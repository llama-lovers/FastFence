"""Frozen, self-authored severity probes against actual local Ollama inference."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.modules.control.persistence.models import SemanticScanner
from fastfence.modules.control.persistence.semantic_severity import (
    OLLAMA_SYSTEM,
    RUBRIC_VERSION,
    SEVERITY_SCORES,
)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    split: Literal["development", "holdout"]
    category: Literal["benign", "suspicious", "malicious"]
    language: Literal["en", "pl"]
    family: str
    text: str = Field(min_length=1, max_length=65536)


def threshold_summary(results: list[dict], threshold: float) -> dict:
    counts = Counter()
    valid = 0
    for result in results:
        expected = SEVERITY_SCORES[result["category"]] >= threshold
        if result["error"] is not None:
            counts["fail_closed_errors"] += 1
            counts[
                "errors_on_expected_block"
                if expected
                else "errors_on_expected_allow"
            ] += 1
            continue
        valid += 1
        blocked = result["score"] >= threshold
        key = (
            "true_positives"
            if expected and blocked
            else "false_negatives"
            if expected
            else "false_positives"
            if blocked
            else "true_negatives"
        )
        counts[key] += 1
    tp, fp, fn = (
        counts[key]
        for key in ("true_positives", "false_positives", "false_negatives")
    )
    return {
        "threshold": threshold,
        "valid_responses": valid,
        **{
            key: counts[key]
            for key in (
                "true_positives",
                "true_negatives",
                "false_positives",
                "false_negatives",
                "fail_closed_errors",
                "errors_on_expected_block",
                "errors_on_expected_allow",
            )
        },
        "precision_on_valid": tp / (tp + fp) if tp + fp else None,
        "recall_on_valid": tp / (tp + fn) if tp + fn else None,
    }


async def evaluate(args: argparse.Namespace) -> dict:
    corpus_bytes = args.corpus.read_bytes()
    all_cases = [
        Case.model_validate_json(line)
        for line in corpus_bytes.splitlines()
        if line.strip()
    ]
    if len({case.id for case in all_cases}) != len(all_cases):
        raise ValueError("Duplicate corpus identifiers")
    cases = [case for case in all_cases if case.split == args.split]
    if not cases:
        raise ValueError("Empty evaluation split")
    scanner = SemanticScanner(args.ollama_url, "http://127.0.0.1:1")
    config = SemanticConfig(
        provider="ollama", model=args.model, timeout_ms=args.timeout_ms
    )
    category_by_score = {
        score: category for category, score in SEVERITY_SCORES.items()
    }
    results = []
    for case in cases:
        result = {
            **case.model_dump(),
            "score": None,
            "predicted_category": None,
            "error": None,
        }
        started = time.perf_counter()
        try:
            assessment = await scanner.assess(
                json.dumps({"query": case.text}, ensure_ascii=False), config
            )
            result.update(
                score=assessment.score,
                predicted_category=category_by_score[assessment.score],
                tokens=assessment.tokens,
            )
        except ModelUnavailableError:
            result["error"] = "model_unavailable_or_invalid_response"
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        results.append(result)
        sys.stdout.write(
            json.dumps(
                {
                    key: result[key]
                    for key in (
                        "id",
                        "category",
                        "predicted_category",
                        "error",
                        "latency_ms",
                    )
                }
            )
            + "\n"
        )
        sys.stdout.flush()
    valid = [result for result in results if result["error"] is None]
    confusion = {
        category: dict(
            Counter(
                result["predicted_category"]
                for result in valid
                if result["category"] == category
            )
        )
        for category in SEVERITY_SCORES
    }
    latencies = sorted(result["latency_ms"] for result in results)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "provider": "actual local Ollama through SemanticScanner",
        "model": args.model,
        "split": args.split,
        "rubric_version": RUBRIC_VERSION,
        "severity_codes": dict(SEVERITY_SCORES),
        "prompt_sha256": hashlib.sha256(OLLAMA_SYSTEM.encode()).hexdigest(),
        "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        "scope": "Semantic component only; self-authored synthetic PL/EN cases, labeled before inference. Development and holdout separate; no external benchmark, production guarantee or calibrated probabilities.",
        "holdout_protocol": "Freeze prompt and complete corpus before holdout; do not tune on holdout. Retain all outputs including mistakes and provider errors.",
        "samples": len(results),
        "errors": len(results) - len(valid),
        "exact_category_accuracy_on_valid": sum(
            result["category"] == result["predicted_category"]
            for result in valid
        )
        / len(valid)
        if valid
        else None,
        "confusion": confusion,
        "thresholds": [
            threshold_summary(results, threshold) for threshold in (0.5, 0.8)
        ],
        "median_latency_ms": statistics.median(latencies),
        "p95_latency_ms": latencies[
            max(0, (len(latencies) * 95 + 99) // 100 - 1)
        ],
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument(
        "--split", choices=["development", "holdout"], required=True
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).with_name("severity_cases.jsonl"),
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    sys.stdout.write(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "samples",
                    "errors",
                    "exact_category_accuracy_on_valid",
                    "confusion",
                    "thresholds",
                )
            },
            indent=2,
        )
        + "\n"
    )
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
