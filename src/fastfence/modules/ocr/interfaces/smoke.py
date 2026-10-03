"""Small synthetic quality check, not a production accuracy or speed benchmark."""

import argparse
import asyncio
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from fastfence.modules.ocr.application.facade import build_ocr
from fastfence.shared.ocr import MediaType, OCRLimits

CASES: tuple[tuple[str, MediaType, tuple[tuple[str, ...], ...]], ...] = (
    (
        "english.png",
        "image/png",
        (("English invoice FIRST PAGE", "alice@example.com"),),
    ),
    (
        "polish.jpg",
        "image/jpeg",
        (("DRUGA STRONA", "Zażółć gęślą jaźń", "44051401458"),),
    ),
    (
        "rotated.png",
        "image/png",
        (("English invoice FIRST PAGE", "alice@example.com"),),
    ),
    (
        "two-pages.pdf",
        "application/pdf",
        (
            ("FIRST PAGE", "alice@example.com"),
            ("DRUGA STRONA", "Zażółć gęślą jaźń", "44051401458"),
        ),
    ),
    (
        "mixed.pdf",
        "application/pdf",
        (
            ("FIRST PAGE", "alice@example.com"),
            ("DRUGA STRONA", "Zażółć gęślą jaźń", "44051401458"),
        ),
    ),
)


async def evaluate(
    python: Path, models: Path, fixtures: Path, repeats: int
) -> dict[str, Any]:
    # Preserve virtualenv interpreter symlinks; resolve() selects base Python.
    runtime = build_ocr(python.absolute(), models.resolve(), OCRLimits())
    results = []
    for name, media, expected in CASES:
        content = (fixtures / name).read_bytes()
        for repeat in range(repeats):
            started = time.monotonic()
            document = await runtime.extract(content, media)
            texts = [
                "\n".join(block.text for block in page.blocks)
                for page in document.pages
            ]
            checks = [len(texts) == len(expected)]
            checks.extend(
                index < len(texts) and phrase in texts[index]
                for index, phrases in enumerate(expected)
                for phrase in phrases
            )
            results.append(
                {
                    "fixture": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "repeat": repeat,
                    "pages": len(document.pages),
                    "checks": len(checks),
                    "checks_passed": sum(checks),
                    "passed": all(checks),
                    "wall_ms": round((time.monotonic() - started) * 1000, 2),
                    "worker_ms": document.elapsed_ms,
                    "confidence_min": min(
                        block.confidence
                        for page in document.pages
                        for block in page.blocks
                    ),
                }
            )
    times = sorted(result["wall_ms"] for result in results)
    return {
        "provider": "paddleocr",
        "models": [
            "PP-LCNet_x1_0_doc_ori",
            "PP-OCRv5_mobile_det",
            "latin_PP-OCRv5_mobile_rec",
        ],
        "scope": "Local synthetic quality checks; every request starts a fresh model worker. No LLM/HTTP timing. Tiny sample, no general accuracy guarantee.",
        "samples": len(results),
        "passed": all(result["passed"] for result in results),
        "p50_wall_ms": statistics.median(times),
        "p95_wall_ms": times[math.ceil(len(times) * 0.95) - 1],
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument(
        "--fixtures", type=Path, default=Path("examples/documents")
    )
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=2)
    parser.add_argument(
        "--output", type=Path, default=Path("evaluation/results/ocr-local.json")
    )
    options = parser.parse_args()
    report = asyncio.run(
        evaluate(
            options.python, options.models, options.fixtures, options.repeats
        )
    )
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise SystemExit(
            "OCR synthetic check failed; inspect content-free report"
        )


if __name__ == "__main__":
    main()
