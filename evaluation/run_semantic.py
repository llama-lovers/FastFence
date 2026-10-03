"""Run public, synthetic holdout probes against the actual semantic model adapter.

This evaluates the semantic component alone. It does not measure the entire gateway,
calibrate model scores, or establish security against arbitrary attacks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.modules.control.persistence.models import SemanticScanner


async def evaluate(args: argparse.Namespace) -> dict:
    cases = [
        json.loads(line)
        for line in args.scenarios.read_text().splitlines()
        if line.strip()
    ]
    scanner = SemanticScanner(args.ollama_url, args.kev_url)
    config = SemanticConfig(
        provider=args.provider,
        model=args.model,
        threshold=args.threshold,
        timeout_ms=args.timeout_ms,
    )
    results = []
    for case in cases:
        started = time.monotonic()
        result = {**case, "score": None, "blocked": None, "error": None}
        try:
            assessment = await scanner.assess(
                json.dumps({"query": case["text"]}), config
            )
            result.update(
                score=assessment.score,
                blocked=assessment.score >= args.threshold,
                tokens=assessment.tokens,
            )
        except ModelUnavailableError:
            result["error"] = "model_unavailable_or_invalid_response"
        result["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
        results.append(result)
        sys.stdout.write(
            json.dumps(
                {k: result[k] for k in ["id", "score", "blocked", "error"]}
            )
            + "\n"
        )
        sys.stdout.flush()

    valid = [r for r in results if r["error"] is None]
    tp = sum(r["malicious"] and r["blocked"] for r in valid)
    tn = sum(not r["malicious"] and not r["blocked"] for r in valid)
    fp = sum(not r["malicious"] and r["blocked"] for r in valid)
    fn = sum(r["malicious"] and not r["blocked"] for r in valid)
    latencies = sorted(r["latency_ms"] for r in results)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "provider": args.provider,
        "model": args.model,
        "threshold": args.threshold,
        "scope": "semantic component only; synthetic development holdout; no security guarantee",
        "summary": {
            "samples": len(results),
            "errors": len(results) - len(valid),
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
            "accuracy_on_valid": (tp + tn) / len(valid) if valid else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "median_latency_ms": statistics.median(latencies)
            if latencies
            else None,
            "p95_latency_ms": latencies[
                min(len(latencies) - 1, int(len(latencies) * 0.95))
            ]
            if latencies
            else None,
        },
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider", choices=["ollama", "kev"], default="ollama"
    )
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--kev-url", default="http://127.0.0.1:8009")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path(__file__).with_name("scenarios.jsonl"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    sys.stdout.write(json.dumps(report["summary"], indent=2) + "\n")
    if report["summary"]["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
