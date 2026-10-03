"""Compose local OCR and public text controls without crossing feature internals."""

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.contracts.dto import Identity, Verdict
from fastfence.modules.ocr.application.facade import OCRRuntime
from fastfence.shared.models import StrictModel
from fastfence.shared.ocr import MediaType, OCRDocument, OCRError


class DocumentResult(StrictModel):
    markdown: str | None
    pages: int
    provider: str
    ocr_elapsed_ms: int
    verdict: Verdict


class DocumentMarkdownWorkflow:
    def __init__(self, ocr: OCRRuntime, control: ControlRuntime) -> None:
        self.ocr, self.control = ocr, control

    async def run(
        self,
        content: bytes,
        media_type: MediaType,
        identity: Identity,
        *,
        model: str | None = None,
        complete: bool = False,
        max_output_tokens: int = 256,
        restore_originals: bool = False,
    ) -> DocumentResult:
        document: OCRDocument | None = None
        failure: OCRError | None = None

        async def source() -> str:
            nonlocal document, failure
            try:
                document = await self.ocr.extract(content, media_type)
                return self.ocr.markdown(document)
            except OCRError as error:
                failure = error
                raise

        verdict, safe = await self.control.process_document(
            identity,
            source,
            timeout_ms=int(self.ocr.limits.timeout_seconds * 1000),
            model=model,
            complete=complete,
            max_output_tokens=max_output_tokens,
            restore_originals=restore_originals,
        )
        if failure is not None:
            raise failure
        if verdict.reason == "document_preparation_timeout":
            raise OCRError("ocr_timeout")
        return DocumentResult(
            markdown=safe,
            pages=len(document.pages) if document is not None else 0,
            provider=document.provider if document is not None else "not_run",
            ocr_elapsed_ms=document.elapsed_ms if document is not None else 0,
            verdict=verdict,
        )
