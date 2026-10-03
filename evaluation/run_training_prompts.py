"""Actual sequential Laya inference on user-supplied synthetic PL/EN prompts."""

import argparse
import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from evaluation.prompt_corpus import CORPUS, classification_summary, load_cases
from fastfence.modules.control.domain.controls import signature_findings
from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import (
    SemanticConfig,
    SignatureFeed,
)
from fastfence.modules.control.persistence.models import SemanticScanner


async def evaluate(args):
    cases = load_cases(args.corpus)
    feed = SignatureFeed.model_validate_json(args.feed.read_text())
    scanner = SemanticScanner(
        args.ollama_url, "http://127.0.0.1:8009", args.root
    )
    config = SemanticConfig(provider="laya", model=args.model, timeout_ms=30000)
    rows = []
    try:
        for case in cases:
            started = time.monotonic()
            row = {
                "id": case.id,
                "source_index": case.source_index,
                "language": case.language,
                "family": case.family,
                "expected_blocked": case.label == "bad_prompt",
                "signature_findings": signature_findings(case.text, feed),
                "blocked": None,
                "score": None,
                "error": None,
            }
            try:
                assessment = await scanner.assess(
                    json.dumps({"prompt": case.text}, ensure_ascii=False),
                    config,
                )
                row.update(
                    score=assessment.score,
                    blocked=assessment.score >= config.threshold,
                    tokens=assessment.tokens,
                )
            except ModelUnavailableError:
                row["error"] = "model_unavailable_or_invalid_response"
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
            rows.append(row)
            print(json.dumps({"sample": len(rows), **row}), flush=True)
    finally:
        await scanner.aclose()
    deterministic = [
        {**row, "blocked": bool(row["signature_findings"]), "error": None}
        for row in rows
    ]
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "Actual Laya semantic component only; synthetic Qwen-generated and Qwen-labelled development corpus, not an independent human-labelled holdout or security certification.",
        "corpus_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
        "feed_sha256": hashlib.sha256(args.feed.read_bytes()).hexdigest(),
        "model": args.model,
        "provider": "laya",
        "threshold": config.threshold,
        "summary": classification_summary(rows),
        "by_language": {
            language: classification_summary(
                [row for row in rows if row["language"] == language]
            )
            for language in ("pl", "en")
        },
        "deterministic_only": classification_summary(deterministic),
        "results": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--feed", type=Path, default=Path("config/signatures.json")
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    if any(
        report["summary"][key]
        for key in ("errors", "false_positives", "false_negatives")
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
