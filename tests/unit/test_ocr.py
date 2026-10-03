"""Pure contracts and worker boundary tests require no downloaded OCR models."""

import asyncio
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from fastfence.modules.ocr.domain.markdown import document_markdown
from fastfence.modules.ocr.persistence.provider import PaddleOCRProvider
from fastfence.shared.ocr import (
    OCRBlock,
    OCRDocument,
    OCRError,
    OCRLimits,
    OCRPage,
)


def document(text="A <script> https://example.test"):
    return OCRDocument(
        pages=[
            OCRPage(
                number=1,
                width=10,
                height=10,
                blocks=[
                    OCRBlock(text=text, confidence=0.1, x=0, y=0),
                ],
            )
        ],
        elapsed_ms=1,
    )


def test_markdown_keeps_untrusted_content_and_explicit_page_order():
    result = document()
    result.pages.append(OCRPage(number=2, width=10, height=10, blocks=[]))
    markdown = document_markdown(result)
    assert "    A <script> https://example.test" in markdown
    assert markdown.index("## Page 1") < markdown.index("## Page 2")
    assert "[No text detected]" in markdown


def test_markdown_rejects_missing_pages_and_oversize():
    result = document()
    result.pages[0].number = 2
    with pytest.raises(OCRError, match="ocr_invalid_result"):
        document_markdown(result)
    with pytest.raises(OCRError, match="ocr_text_limit"):
        document_markdown(document("ą" * 100), max_bytes=100)


def test_limits_and_confidence_are_validated():
    with pytest.raises(ValidationError):
        OCRLimits(max_pages=100)
    with pytest.raises(ValidationError):
        OCRBlock(text="word", confidence=float("nan"), x=0, y=0)
    limits = OCRLimits()
    with pytest.raises(ValidationError):
        limits.max_pages = 20


def test_worker_errors_never_expose_raw_provider_content():
    for raw in (b"raw secret traceback", b'{"error":"sensitive details"}'):
        with pytest.raises(OCRError) as error:
            PaddleOCRProvider._result(raw, 1)
        assert "sensitive" not in str(error.value)
        assert "traceback" not in str(error.value)


@pytest.mark.asyncio
async def test_missing_provider_and_oversize_fail_before_worker():
    provider = PaddleOCRProvider(None, None, OCRLimits(max_bytes=1024))
    with pytest.raises(OCRError, match="ocr_unavailable"):
        await provider.extract(b"input", "image/png")
    with pytest.raises(OCRError, match="ocr_input_limit"):
        await provider.extract(b"x" * 1025, "image/png")


@pytest.mark.asyncio
async def test_worker_concurrency_and_timeout_are_bounded():
    class SlowFixtureProvider(PaddleOCRProvider):
        async def _run(self, content, media_type):
            await asyncio.sleep(2)
            return document()

    provider = SlowFixtureProvider(
        Path("fixture"), Path("fixture"), OCRLimits(timeout_seconds=1)
    )
    first = asyncio.create_task(provider.extract(b"x", "image/png"))
    await asyncio.sleep(0)
    with pytest.raises(OCRError, match="ocr_busy"):
        await provider.extract(b"x", "image/png")
    with pytest.raises(OCRError, match="ocr_timeout"):
        await first
    assert not provider._slot.locked()


@pytest.mark.asyncio
async def test_timeout_kills_real_worker_process(monkeypatch):
    spawn = asyncio.create_subprocess_exec
    processes = []

    async def slow_worker(*args, **kwargs):
        process = await spawn(
            sys.executable, "-c", "import time; time.sleep(10)", **kwargs
        )
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", slow_worker)
    provider = PaddleOCRProvider(
        Path(sys.executable), Path("fixture"), OCRLimits(timeout_seconds=1)
    )
    with pytest.raises(OCRError, match="ocr_timeout"):
        await provider.extract(b"x", "image/png")
    assert len(processes) == 1
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_worker_output_bound_kills_oversized_result(monkeypatch):
    spawn = asyncio.create_subprocess_exec
    processes = []

    async def oversized_worker(*args, **kwargs):
        process = await spawn(
            sys.executable,
            "-c",
            "import sys,time; sys.stdout.write('x'*3000000); sys.stdout.flush(); time.sleep(10)",
            **kwargs,
        )
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", oversized_worker)
    provider = PaddleOCRProvider(
        Path(sys.executable), Path("fixture"), OCRLimits(timeout_seconds=5)
    )
    with pytest.raises(OCRError, match="ocr_text_limit"):
        await provider.extract(b"x", "image/png")
    assert processes[0].returncode is not None
