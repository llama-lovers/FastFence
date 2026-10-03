"""Authenticated binary upload; only approved Markdown can be exported."""

from typing import Annotated, Literal, cast

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.ocr.application.facade import build_ocr
from fastfence.shared.ocr import MediaType, OCRError, OCRLimits
from fastfence.shared.settings.app_settings import AppSettings
from fastfence.workflows.document_markdown import DocumentMarkdownWorkflow


async def _body(request: Request, maximum: int) -> bytes:
    length = request.headers.get("content-length")
    if length is not None:
        try:
            valid_length = 0 <= int(length) <= maximum
        except ValueError:
            valid_length = False
        if not valid_length:
            raise HTTPException(413, "Document exceeds upload limit")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > maximum:
            raise HTTPException(413, "Document exceeds upload limit")
        data.extend(chunk)
    return bytes(data)


def _ocr_status(error: OCRError) -> int:
    if error.reason in {"ocr_unavailable", "ocr_busy"}:
        return 503
    if error.reason == "ocr_timeout":
        return 504
    if error.reason in {
        "ocr_input_limit",
        "ocr_page_limit",
        "ocr_pixel_limit",
        "ocr_text_limit",
    }:
        return 413
    return 422


def configure_documents(
    app: FastAPI, runtime: ControlRuntime, settings: AppSettings
) -> None:
    limits = OCRLimits(
        timeout_seconds=settings.ocr_timeout_seconds,
        max_pages=settings.ocr_max_pages,
        max_page_pixels=settings.ocr_max_pixels,
        max_total_pixels=settings.ocr_max_total_pixels,
    )
    ocr = build_ocr(settings.ocr_python, settings.ocr_models, limits)
    workflow = DocumentMarkdownWorkflow(ocr, runtime)
    app.state.document_workflow = workflow

    @app.post("/api/documents/markdown", response_model=None)
    async def document_markdown(
        request: Request,
        mode: Literal["extract", "complete"] = "extract",
        model: Annotated[
            str | None, Query(min_length=1, max_length=100)
        ] = None,
        max_output_tokens: Annotated[int, Query(ge=1, le=2048)] = 256,
        restore_originals: bool = False,
        download: bool = False,
    ) -> JSONResponse | PlainTextResponse:
        authorization = request.headers.get("authorization", "")
        token = (
            authorization[7:] if authorization.startswith("Bearer ") else None
        )
        identity = runtime.authenticate(token)
        if identity is None:
            raise HTTPException(401, "Verified bearer credential required")
        if identity.admin:
            raise HTTPException(403, "Agent credential required")
        media = (
            request.headers.get("content-type", "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if media not in {"image/png", "image/jpeg", "application/pdf"}:
            raise HTTPException(415, "Use PNG, JPEG or PDF document bytes")
        if download and mode != "extract":
            raise HTTPException(422, "Markdown download requires extract mode")
        if restore_originals and mode != "complete":
            raise HTTPException(422, "Restoration requires complete mode")
        content = await _body(request, limits.max_bytes)
        try:
            result = await workflow.run(
                content,
                cast(MediaType, media),
                identity,
                model=model,
                complete=mode == "complete",
                max_output_tokens=max_output_tokens,
                restore_originals=restore_originals,
            )
        except OCRError as error:
            raise HTTPException(_ocr_status(error), error.reason) from None
        if download and result.markdown is not None:
            return PlainTextResponse(
                result.markdown,
                media_type="text/markdown",
                headers={
                    "Content-Disposition": 'attachment; filename="document.md"',
                    "Cache-Control": "no-store",
                },
            )
        status = (
            200 if result.verdict.decision in {"allowed", "redacted"} else 422
        )
        return JSONResponse(
            result.model_dump(mode="json"),
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )
