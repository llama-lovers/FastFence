from typing import Protocol

from fastfence.shared.ocr import MediaType, OCRDocument


class OCRPort(Protocol):
    async def extract(
        self, content: bytes, media_type: MediaType
    ) -> OCRDocument: ...
