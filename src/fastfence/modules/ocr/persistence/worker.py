"""Single killable OCR job, binary stdin and bounded JSON stdout."""

import contextlib
import importlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

from fastfence.shared.ocr import (
    MediaType,
    OCRBlock,
    OCRDocument,
    OCRError,
    OCRLimits,
    OCRPage,
)


def recognize(
    content: bytes, media: MediaType, root: Path, limits: OCRLimits
) -> OCRDocument:
    np = importlib.import_module("numpy")

    from fastfence.modules.ocr.persistence.media import decoded_pages
    from fastfence.modules.ocr.persistence.models import load_models

    started = time.monotonic()
    pipeline = load_models(root)
    pages, text_bytes = [], 0
    for number, image in enumerate(decoded_pages(content, media, limits), 1):
        results = list(pipeline.predict(np.asarray(image)))
        if len(results) != 1:
            raise OCRError("ocr_page_failed")
        blocks = _blocks(results[0])
        text_bytes += sum(len(block.text.encode()) for block in blocks)
        if text_bytes > limits.max_text_bytes:
            raise OCRError("ocr_text_limit")
        pages.append(
            OCRPage(
                number=number,
                width=image.width,
                height=image.height,
                blocks=blocks,
            )
        )
        image.close()
    return OCRDocument(
        pages=pages, elapsed_ms=int((time.monotonic() - started) * 1000)
    )


def _blocks(result: Any) -> list[OCRBlock]:
    texts, scores, polygons = (
        result["rec_texts"],
        result["rec_scores"],
        result["rec_polys"],
    )
    if (
        len(texts) != len(scores)
        or len(texts) != len(polygons)
        or len(texts) > 2000
    ):
        raise OCRError("ocr_page_failed")
    blocks = []
    for text, confidence, polygon in zip(texts, scores, polygons, strict=True):
        if not text.strip():
            continue
        blocks.append(
            OCRBlock(
                text=text,
                confidence=float(confidence),
                x=max(0, min(float(p[0]) for p in polygon)),
                y=max(0, min(float(p[1]) for p in polygon)),
            )
        )
    return sorted(blocks, key=lambda block: (round(block.y / 12), block.x))


def main() -> None:
    output = sys.stdout
    from fastfence.modules.ocr.persistence.isolation import disable_network

    disable_network()
    try:
        media = cast(MediaType, sys.argv[1])
        if media not in {"image/png", "image/jpeg", "application/pdf"}:
            raise OCRError("ocr_unsupported_media")
        limits = OCRLimits.model_validate_json(sys.argv[3])
        content = sys.stdin.buffer.read(limits.max_bytes + 1)
        with (
            open(os.devnull, "w") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            document = recognize(content, media, Path(sys.argv[2]), limits)
        output.write(document.model_dump_json())
    except OCRError as error:
        output.write(json.dumps({"error": error.reason}))
        raise SystemExit(1) from None
    except Exception:
        output.write('{"error":"ocr_page_failed"}')
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
