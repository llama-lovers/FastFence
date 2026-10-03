"""Evaluate inert historical attack marker variants; execute no payload code."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from fastfence.modules.control.domain.controls import signature_findings
from fastfence.modules.control.domain.models import SignatureFeed


class HistoricalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    family: str
    variant: str
    malicious_marker: bool
    desired_signature_block: bool
    payload: Any


def validate(corpus: Path, feed_path: Path) -> dict:
    source = json.loads(corpus.read_text())
    cases = [HistoricalCase.model_validate(row) for row in source["cases"]]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Historical corpus IDs must be unique")
    feed = SignatureFeed.model_validate_json(feed_path.read_text())
    results, counts = (
        [],
        Counter(
            dict.fromkeys(
                [
                    "true_positive",
                    "false_negative",
                    "true_negative",
                    "false_positive",
                ],
                0,
            )
        ),
    )
    for case in cases:
        findings = signature_findings(case.payload, feed)
        blocked = bool(findings)
        counts[
            "true_positive"
            if blocked and case.malicious_marker
            else "false_negative"
            if case.malicious_marker
            else "false_positive"
            if blocked
            else "true_negative"
        ] += 1
        results.append(
            {
                "id": case.id,
                "family": case.family,
                "variant": case.variant,
                "expected_block": case.desired_signature_block,
                "actual_signature_block": blocked,
                "matched_signature_ids": findings,
                "expectation_met": blocked == case.desired_signature_block,
            }
        )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "corpus": str(corpus),
        "feed_version": feed.version,
        "signature_count": len(feed.signatures),
        "scope": "Historical signature component only; synthetic inert strings/JSON, no code execution, no model inference, no claim that encoded text itself executes",
        "corpus_scope": source["scope"],
        "sources": source["sources"],
        "sample_count": len(cases),
        "summary": dict(counts),
        "results": results,
        "limitations": [
            "Literal markers are contextual clues rather than proof of exploit execution",
            "Decoding is bounded to one layer and 4096-character base64 tokens; nested/long encodings and nonconfigured patterns remain outside coverage",
            "Quoted educational examples can trigger false positives; semantic context is not assessed here",
            "This report does not evaluate full pipeline privacy, authorization or semantic mitigation",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("evaluation/historical_attacks.json"),
    )
    parser.add_argument(
        "--feed", type=Path, default=Path("config/signatures.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.corpus, args.feed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"Recorded {report['sample_count']} inert cases including limitations: {args.output}"
    )
