"""Compose local OCR and public text controls without crossing feature internals."""

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.contracts.dto import Identity, Verdict
from fastfence.modules.ocr.application.facade import OCRRuntime
from fastfence.shared.models import StrictModel
from fastfence.shared.ocr import MediaType


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
        document = await self.ocr.extract(content, media_type)
        markdown = self.ocr.markdown(document)
        if complete:
            verdict, safe = await self.control.complete_document(
                identity,
                markdown,
                model=model,
                max_output_tokens=max_output_tokens,
                restore_originals=restore_originals,
            )
        else:
            verdict = await self.control.prepare_document(
                identity, markdown, model=model
            )
            safe = (
                verdict.output.get("markdown")
                if verdict.decision in {"allowed", "redacted"}
                and isinstance(verdict.output, dict)
                else None
            )
        return DocumentResult(
            markdown=safe,
            pages=len(document.pages),
            provider=document.provider,
            ocr_elapsed_ms=document.elapsed_ms,
            verdict=verdict,
        )
