"""Compare actual deterministic Engine work; upstream is a zero-wait fixture."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import itertools
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

if __package__:
    from evaluation.benchmark_gateway import (
        engine_for,
        hardware,
        percentiles,
        prepare_configuration,
    )
else:
    from benchmark_gateway import (
        engine_for,
        hardware,
        percentiles,
        prepare_configuration,
    )

from fastfence.modules.control.domain.models import Identity, ToolCall


async def measure(
    root: Path,
    size: str,
    rules: int,
    concurrency: int,
    samples: int,
    warmup: int,
) -> dict:
    policy_path = root / "policy.yaml"
    policy = yaml.safe_load(policy_path.read_text())
    policy["text_rules"] = [
        {
            "id": f"benchmark-{index:02}",
            "operator": "contains",
            "value": f"blocked-marker-{index:02}",
            "direction": "input",
            "target": "tool",
            "action": "block",
            "case_sensitive": False,
        }
        for index in range(rules)
    ]
    policy_path.write_text(yaml.safe_dump(policy))
    engine = engine_for(
        root, f"scan-{size}-{rules}-{concurrency}", "zero_wait_fixture"
    )
    identity = Identity(
        subject="benchmark-analyst", tenant="blue", roles=["analyst"]
    )
    query = (
        "Approved quarterly business summary"
        if size == "short"
        else ("Approved business summary " * 310)[:8000]
    )
    call = ToolCall(tool="knowledge.search", arguments={"query": query})
    latencies: list[float] = []
    tickets = itertools.count()

    async def invoke() -> float:
        started = time.perf_counter_ns()
        verdict = await engine.invoke(identity, call)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        if (verdict.decision, verdict.reason, verdict.upstream_executed) != (
            "allowed",
            "controls_passed",
            True,
        ):
            raise AssertionError("Unexpected deterministic benchmark verdict")
        return elapsed

    async def worker() -> None:
        while next(tickets) < samples:
            latencies.append(await invoke())
            if concurrency > 1:
                await asyncio.sleep(0)

    try:
        for _ in range(warmup):
            await invoke()
        started = time.perf_counter_ns()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        seconds = (time.perf_counter_ns() - started) / 1_000_000_000
        metrics = engine.ledger.stats()
        budgets = engine.ledger.budgets()
        assert metrics["requests"] == samples + warmup
        assert (
            metrics["allowed"] == samples + warmup
            and metrics["semantic_calls"] == 0
        )
        assert sum(row["calls"] for row in budgets) == samples + warmup
        assert all(row["inflight"] == 0 for row in budgets)
        assert len(engine.ledger.audit(10_000)) == min(256, samples + warmup)
        return {
            "payload_class": size,
            "query_utf8_bytes": len(query.encode()),
            "rules": rules,
            "concurrency": concurrency,
            "samples": samples,
            "warmup_excluded_from_timing": warmup,
            "wall_seconds": round(seconds, 6),
            "throughput_rps": round(samples / seconds, 3),
            **percentiles(latencies),
            "all_verdicts_and_accounting_passed": True,
        }
    finally:
        engine.ledger.close()


async def benchmark(args: argparse.Namespace) -> dict:
    reports = []
    with TemporaryDirectory(prefix="fastfence-scan-benchmark-") as temporary:
        root = Path(temporary)
        prepare_configuration(root, args.samples, args.warmup, 8)
        for size, rules, concurrency in itertools.product(
            ["short", "near_tool_limit"], [0, 64], [1, 8]
        ):
            reports.append(
                await measure(
                    root, size, rules, concurrency, args.samples, args.warmup
                )
            )
    return {
        "phase": args.phase,
        "created_at": datetime.now(UTC).isoformat(),
        "environment": hardware(),
        "source_sha256": {
            path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in [
                "src/fastfence/modules/control/domain/signature_matching.py",
                "src/fastfence/modules/control/persistence/secrets.py",
                "evaluation/benchmark_scan_optimization.py",
            ]
        },
        "scope": "Actual Engine authorization, schema validation, deterministic input/output inspection, memory budget reserve/settle and audit; zero-wait simulated tools; no HTTP/MCP or model inference.",
        "limitations": [
            "Self-authored clean synthetic business inputs on one development machine, not a production latency guarantee.",
            "Concurrency8 schedules cooperating tasks on one event loop; individual timers measure Engine execution, not transport queue latency.",
            "Startup, policy construction and invariant checks are outside request timing; warmup remains in accounting.",
        ],
        "results": reports,
        "all_passed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["before", "after"], required=True)
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1 or args.warmup < 0:
        parser.error("Samples must be positive and warmup nonnegative")
    report = asyncio.run(benchmark(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for row in report["results"]:
        print(json.dumps(row))


if __name__ == "__main__":
    main()
