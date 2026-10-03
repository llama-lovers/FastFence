"""Outcome/accounting invariants and honest end-to-end timing summaries."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field


class Workload(BaseModel):
    name: str
    query: str
    decision: str
    reason: str


class Proof(BaseModel):
    invocations: int = 0
    calls: int = 0
    tokens: int = 0
    cost: int = 0
    versions: set[tuple[int, int]] = Field(default_factory=set)
    identifiers: set[str] = Field(default_factory=set)

    def record(self, verdict: dict[str, Any], workload: Workload) -> None:
        expected = workload.decision == "allowed"
        if (
            verdict["decision"],
            verdict["reason"],
            verdict["upstream_executed"],
        ) != (workload.decision, workload.reason, expected):
            raise ValueError(
                f"Unexpected verdict for {workload.name}: {verdict['decision']}/{verdict['reason']}; timing invalidated, including budget denial"
            )
        identifier = verdict["request_id"]
        if identifier in self.identifiers:
            raise ValueError("Repeated request ID invalidates audit evidence")
        self.identifiers.add(identifier)
        self.invocations += 1
        self.calls += int(expected)
        self.tokens += verdict["tokens"]
        self.cost += verdict["cost_microusd"]
        self.versions.add((verdict["policy_version"], verdict["feed_version"]))

    def verify(
        self, status: dict[str, Any], audit: list[dict[str, Any]]
    ) -> None:
        rows = [row for row in audit if row["event_kind"] == "invocation"]
        if {row["request_id"] for row in rows} != self.identifiers or len(
            rows
        ) != self.invocations:
            raise ValueError(
                "Invocation audit missing, duplicated or truncated"
            )
        budgets = [
            row for row in status["budgets"] if row["subject"] == "analyst-blue"
        ]
        if len(budgets) != 1:
            raise ValueError("Expected exactly one subject accounting entry")
        budget = budgets[0]
        actual = (
            budget["calls"],
            budget["tokens"],
            budget["cost_microusd"],
            budget["inflight"],
        )
        if actual != (self.calls, self.tokens, self.cost, 0):
            raise ValueError(
                "Warmup/measured budget totals do not match actual verdicts"
            )
        if (
            status["metrics"]["requests"] != self.invocations
            or status["metrics"]["semantic_calls"] != 0
        ):
            raise ValueError(
                "Request/semantic counts inconsistent with model-free benchmark"
            )


def percentile(values: list[float], fraction: float) -> float:
    return sorted(values)[
        min(len(values) - 1, max(0, math.ceil(len(values) * fraction) - 1))
    ]


async def measure(
    invoke: Callable[[], Awaitable[Any]],
    count: int,
    concurrency: int,
    validate: Callable[[Any], None] | None = None,
) -> tuple[list[float], float]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one() -> float:
        async with semaphore:
            started = time.perf_counter()
            result = await invoke()
            elapsed = (time.perf_counter() - started) * 1000
            if validate is not None:
                validate(result)
            return elapsed

    started = time.perf_counter()
    timings = await asyncio.gather(*(one() for _ in range(count)))
    return timings, time.perf_counter() - started


def summary(values: list[float], seconds: float) -> dict[str, Any]:
    return {
        "samples": len(values),
        "p50_ms": round(percentile(values, 0.50), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
        "wall_seconds": round(seconds, 6),
        "throughput_rps": round(len(values) / seconds, 3),
        "transport_errors": 0,
        "unexpected_verdicts": 0,
    }
