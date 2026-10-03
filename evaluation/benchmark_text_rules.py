"""Measure authored local matching separately from complete gateway overhead."""

import argparse
import json
import math
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

from fastfence.modules.control.domain.text_rules import (
    TextRule,
    text_rule_findings,
)


def benchmark(samples: int) -> dict:
    results = []
    for count in (1, 16, 64):
        rules = tuple(
            TextRule(
                id=f"rule-{index}",
                operator="contains",
                value=f"forbidden-token-{index}",
                case_sensitive=bool(index % 2),
            )
            for index in range(count)
        )
        for length in (128, 4096, 65536):
            text = ("Hello world " * (length // 12 + 1))[:length]
            payload = {"prompt": text}
            timings = []
            for index in range(samples + 100):
                start = time.perf_counter_ns()
                findings = text_rule_findings(rules, payload, "input", "model")
                elapsed = (time.perf_counter_ns() - start) / 1_000_000
                assert not findings
                if index >= 100:
                    timings.append(elapsed)
            timings.sort()
            results.append(
                {
                    "rule_count": count,
                    "content_bytes": len(text.encode()),
                    "samples": samples,
                    **{
                        f"p{percent}_ms": round(
                            timings[math.ceil(samples * percent / 100) - 1], 6
                        )
                        for percent in (50, 95, 99)
                    },
                }
            )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "scope": "Local authored text-rule matching only; all rules miss; excludes startup, privacy, budgets, audit, HTTP/MCP and model calls. Fixed ASCII payloads; not a performance guarantee.",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "warmup_per_case": 100,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 100:
        parser.error("Use at least 100 measured samples per case")
    report = benchmark(args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for result in report["results"]:
        print(json.dumps(result))
