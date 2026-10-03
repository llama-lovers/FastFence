"""Optional-extra decoder tests; ordinary text installs need no media libraries."""

from pathlib import Path

import pytest

from fastfence.modules.ocr.persistence.media import decoded_pages
from fastfence.shared.ocr import OCRError, OCRLimits


@pytest.fixture(autouse=True)
def media_libraries():
    pytest.importorskip("PIL")
    pytest.importorskip("pypdfium2")


@pytest.mark.parametrize(
    ("name", "media", "pages"),
    [
        ("english.png", "image/png", 1),
        ("polish.jpg", "image/jpeg", 1),
        ("two-pages.pdf", "application/pdf", 2),
        ("mixed.pdf", "application/pdf", 2),
    ],
)
def test_local_media_decoding_preserves_all_pages(name, media, pages):
    content = (Path("examples/documents") / name).read_bytes()
    result = list(decoded_pages(content, media, OCRLimits()))
    assert len(result) == pages
    for image in result:
        assert image.width > 0 and image.height > 0
        image.close()


@pytest.mark.parametrize(
    ("content", "media"),
    [(b"corrupt", "image/png"), (b"%PDF-invalid", "application/pdf")],
)
def test_corrupt_inputs_fail_instead_of_returning_partial_document(
    content, media
):
    with pytest.raises(OCRError, match="ocr_invalid_media"):
        list(decoded_pages(content, media, OCRLimits()))


def test_decoders_reject_declared_format_mismatch():
    with pytest.raises(OCRError, match="ocr_invalid_media"):
        list(
            decoded_pages(
                Path("examples/documents/english.png").read_bytes(),
                "image/jpeg",
                OCRLimits(),
            )
        )


def test_pdf_page_and_pixel_limits_reject_not_truncate():
    data = Path("examples/documents/two-pages.pdf").read_bytes()
    with pytest.raises(OCRError, match="ocr_page_limit"):
        list(decoded_pages(data, "application/pdf", OCRLimits(max_pages=1)))
    with pytest.raises(OCRError, match="ocr_pixel_limit"):
        list(
            decoded_pages(
                data, "application/pdf", OCRLimits(max_page_pixels=1000)
            )
        )
    with pytest.raises(OCRError, match="ocr_pixel_limit"):
        list(
            decoded_pages(
                data, "application/pdf", OCRLimits(max_total_pixels=1_000_000)
            )
        )
