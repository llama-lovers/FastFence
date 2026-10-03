"""Provider-independent, bounded local OCR results."""

from typing import Literal

from pydantic import ConfigDict, Field

from fastfence.shared.models import StrictModel

type MediaType = Literal["image/png", "image/jpeg", "application/pdf"]


class OCRLimits(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_bytes: int = Field(
        default=10 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024
    )
    max_pages: int = Field(default=10, ge=1, le=20)
    max_page_pixels: int = Field(default=20_000_000, ge=1000, le=40_000_000)
    max_total_pixels: int = Field(default=80_000_000, ge=1000, le=160_000_000)
    max_text_bytes: int = Field(default=65_536, ge=1024, le=262_144)
    timeout_seconds: float = Field(default=60, ge=1, le=180)


class OCRBlock(StrictModel):
    text: str = Field(min_length=1, max_length=8192)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)


class OCRPage(StrictModel):
    number: int = Field(ge=1, le=20)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    blocks: list[OCRBlock] = Field(max_length=2000)


class OCRDocument(StrictModel):
    provider: Literal["paddleocr"] = "paddleocr"
    pages: list[OCRPage] = Field(min_length=1, max_length=20)
    elapsed_ms: int = Field(ge=0)


class OCRError(Exception):
    """Only static, content-free reasons leave the provider boundary."""

    def __init__(self, reason: str) -> None:
        allowed = {
            "ocr_unavailable",
            "ocr_busy",
            "ocr_timeout",
            "ocr_invalid_media",
            "ocr_unsupported_media",
            "ocr_encrypted_pdf",
            "ocr_page_limit",
            "ocr_pixel_limit",
            "ocr_text_limit",
            "ocr_input_limit",
            "ocr_page_failed",
            "ocr_invalid_result",
        }
        self.reason = reason if reason in allowed else "ocr_page_failed"
        super().__init__(self.reason)
