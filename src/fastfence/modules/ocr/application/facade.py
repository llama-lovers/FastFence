from pathlib import Path

from fastfence.modules.ocr.contracts.ports import OCRPort
from fastfence.modules.ocr.domain.markdown import document_markdown
from fastfence.modules.ocr.persistence.provider import PaddleOCRProvider
from fastfence.shared.ocr import MediaType, OCRDocument, OCRLimits


class OCRRuntime:
    def __init__(self, provider: OCRPort, limits: OCRLimits) -> None:
        self.provider = provider
        self.limits = limits

    async def extract(
        self, content: bytes, media_type: MediaType
    ) -> OCRDocument:
        return await self.provider.extract(content, media_type)

    def markdown(self, document: OCRDocument) -> str:
        return document_markdown(document, self.limits.max_text_bytes)


def build_ocr(
    python: Path | None, models: Path | None, limits: OCRLimits
) -> OCRRuntime:
    return OCRRuntime(PaddleOCRProvider(python, models, limits), limits)
