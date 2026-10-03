"""Decode/render request-local bytes with page and pixel checks before allocation."""

import importlib
import io
import math
from collections.abc import Iterator
from typing import Any

from fastfence.shared.ocr import MediaType, OCRError, OCRLimits


def _pixels(width: int, height: int, total: int, limits: OCRLimits) -> int:
    pixels = width * height
    total += pixels
    if pixels > limits.max_page_pixels or total > limits.max_total_pixels:
        raise OCRError("ocr_pixel_limit")
    return total


def image_pages(
    content: bytes, media: MediaType, limits: OCRLimits
) -> Iterator[Any]:
    image_module = importlib.import_module("PIL.Image")
    image_ops = importlib.import_module("PIL.ImageOps")

    try:
        with image_module.open(io.BytesIO(content)) as original:
            expected = "PNG" if media == "image/png" else "JPEG"
            if (
                original.format != expected
                or getattr(original, "n_frames", 1) != 1
            ):
                raise OCRError("ocr_invalid_media")
            _pixels(original.width, original.height, 0, limits)
            normalized = image_ops.exif_transpose(original)
            yield normalized.convert("RGB")
    except OCRError:
        raise
    except Exception:
        raise OCRError("ocr_invalid_media") from None


def pdf_pages(content: bytes, limits: OCRLimits) -> Iterator[Any]:
    pdfium = importlib.import_module("pypdfium2")

    if not content.startswith(b"%PDF-"):
        raise OCRError("ocr_invalid_media")
    try:
        document = pdfium.PdfDocument(content)
    except Exception:
        # PDFium's password code does not expose document text.
        if pdfium.raw.FPDF_GetLastError() == pdfium.raw.FPDF_ERR_PASSWORD:
            raise OCRError("ocr_encrypted_pdf") from None
        raise OCRError("ocr_invalid_media") from None
    with document:
        if pdfium.raw.FPDF_GetSecurityHandlerRevision(document.raw) != -1:
            raise OCRError("ocr_encrypted_pdf")
        if not 1 <= len(document) <= limits.max_pages:
            raise OCRError("ocr_page_limit")
        total = 0
        for index in range(len(document)):
            page = document[index]
            try:
                width, height = page.get_size()
                total = _pixels(
                    math.ceil(width * 2), math.ceil(height * 2), total, limits
                )
                bitmap = page.render(scale=2)
                try:
                    yield bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()


def decoded_pages(
    content: bytes, media: MediaType, limits: OCRLimits
) -> Iterator[Any]:
    if not content or len(content) > limits.max_bytes:
        raise OCRError("ocr_input_limit")
    yield from (
        pdf_pages(content, limits)
        if media == "application/pdf"
        else image_pages(content, media, limits)
    )
