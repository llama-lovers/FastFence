from __future__ import annotations

import copy
import threading
import time
from collections import Counter, deque
from datetime import UTC, datetime
from itertools import islice
from typing import Any

from pydantic import Field

from fastfence.modules.control.domain.exceptions import BudgetExceededError
from fastfence.modules.control.domain.frozen import FrozenControlModel
from fastfence.modules.control.domain.models import Limits, Verdict
from fastfence.shared.models import StrictModel


class _Budget(StrictModel):
    calls: int = 0
    tokens: int = 0
    cost_microusd: int = 0
    compute_ms: int = 0


class _Reservation(FrozenControlModel):
    day: str
    subject: str
    tokens: int = Field(ge=0)
    cost: int = Field(ge=0)
    ms: int = Field(ge=0)


class _TrafficBucket(StrictModel):
    second: int = -1
    count: int = 0


class Ledger:
    """Atomic, bounded process-local accounting. Restart deliberately resets it."""

    def __init__(self, *, instance_id: str, audit_limit: int = 10_000) -> None:
        if not instance_id or not 1 <= audit_limit <= 100_000:
            raise ValueError("Instance ID and bounded audit capacity required")
        self.instance_id, self.audit_limit = instance_id, audit_limit
        self._lock = threading.RLock()
        self._closed = False
        self._day = self.day()
        self._budgets: dict[tuple[str, str], _Budget] = {}
        self._reservations: dict[str, _Reservation] = {}
        self._inflight: Counter[str] = Counter()
        self._daily_inflight: Counter[tuple[str, str]] = Counter()
        self._audit: deque[dict[str, Any]] = deque(maxlen=audit_limit)
        self._latencies: deque[int] = deque(maxlen=2048)
        self._traffic = [_TrafficBucket() for _ in range(60)]
        self._counters: Counter[str] = Counter()
        self._sequence = 0
        self._started = time.monotonic()

    @staticmethod
    def day() -> str:
        return datetime.now(UTC).date().isoformat()

    def reserve(
        self,
        request_id: str,
        subject: str,
        limits: Limits,
        tokens: int,
        cost: int,
        ms: int,
    ) -> None:
        with self._lock:
            self._ensure_open()
            if request_id in self._reservations:
                raise ValueError("Request already reserved")
            day = self.day()
            reservation = _Reservation(
                day=day, subject=subject, tokens=tokens, cost=cost, ms=ms
            )
            self._rollover(day)
            key = (day, subject)
            budget = self._budgets.get(key)
            if budget is None:
                budget = _Budget()
            checks = (
                ("calls", budget.calls + 1, limits.calls),
                ("tokens", budget.tokens + tokens, limits.tokens),
                (
                    "cost_microusd",
                    budget.cost_microusd + cost,
                    limits.cost_microusd,
                ),
                ("compute_ms", budget.compute_ms + ms, limits.compute_ms),
                ("inflight", self._inflight[subject] + 1, limits.concurrent),
            )
            for name, usage, maximum in checks:
                if usage > maximum:
                    raise BudgetExceededError(f"budget_{name}")
            budget.calls += 1
            budget.tokens += tokens
            budget.cost_microusd += cost
            budget.compute_ms += ms
            self._budgets[key] = budget
            self._inflight[subject] += 1
            self._daily_inflight[key] += 1
            self._reservations[request_id] = reservation

    def settle(
        self, request_id: str, tokens: int, cost: int, compute_ms: int
    ) -> None:
        with self._lock:
            row = self._reservations.pop(request_id, None)
            if row is None:
                return
            key = (row.day, row.subject)
            budget = self._budgets[key]
            budget.tokens += max(0, min(tokens, row.tokens)) - row.tokens
            budget.cost_microusd += max(0, min(cost, row.cost)) - row.cost
            budget.compute_ms += max(0, min(compute_ms, row.ms)) - row.ms
            self._inflight[row.subject] -= 1
            self._daily_inflight[key] -= 1
            if not self._daily_inflight[key]:
                del self._daily_inflight[key]
            if row.day != self._day and not self._daily_inflight[key]:
                self._budgets.pop(key, None)

    def append(
        self, subject: str, tenant: str, target: str, verdict: Verdict
    ) -> None:
        verdict.instance_id = self.instance_id
        record = verdict.model_dump(exclude={"output"})
        with self._lock:
            self._sequence += 1
            self._audit.append(
                {
                    "sequence": self._sequence,
                    "time": datetime.now(UTC).isoformat(),
                    "subject": subject,
                    "tenant": tenant,
                    "target": target,
                    **record,
                }
            )
            if not target.startswith("policy."):
                self._count_request(verdict)

    def record_semantic_call(self) -> None:
        with self._lock:
            self._counters["semantic_calls"] += 1

    def _count_request(self, verdict: Verdict) -> None:
        self._counters["requests"] += 1
        self._counters[
            "errors" if verdict.decision == "error" else verdict.decision
        ] += 1
        self._latencies.append(verdict.latency_ms)
        second = int(time.monotonic())
        bucket = self._traffic[second % len(self._traffic)]
        if bucket.second != second:
            bucket.second, bucket.count = second, 0
        bucket.count += 1

    def audit(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            # Copies are bounded reads; callers cannot alter the internal audit ring.
            return copy.deepcopy(
                list(
                    islice(
                        reversed(self._audit),
                        max(0, min(limit, self.audit_limit)),
                    )
                )
            )

    def budgets(self) -> list[dict[str, Any]]:
        with self._lock:
            day = self.day()
            self._rollover(day)
            return [
                {
                    "day": date,
                    "subject": subject,
                    **budget.model_dump(),
                    "inflight": self._inflight[subject],
                    "instance_id": self.instance_id,
                    "telemetry_scope": "instance",
                }
                for (date, subject), budget in sorted(self._budgets.items())
                if date == day
            ]

    def stats(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            counts = {
                key: self._counters[key]
                for key in (
                    "requests",
                    "allowed",
                    "blocked",
                    "redacted",
                    "errors",
                    "semantic_calls",
                )
            }
            latencies = sorted(self._latencies)
            recent = sum(
                bucket.count
                for bucket in self._traffic
                if 0 <= int(now) - bucket.second < 60
            )
            retained = len(self._audit)
            sequence = self._sequence
        window = max(0.001, min(now - self._started, 60))
        return {
            **counts,
            "p95_latency_ms": latencies[
                min(len(latencies) - 1, int(len(latencies) * 0.95))
            ]
            if latencies
            else 0,
            "latency_sample_size": len(latencies),
            "throughput_rps": round(recent / window, 3),
            "throughput_window_seconds": round(window, 3),
            "audit_retained": retained,
            "audit_dropped": sequence - retained,
            **self.scope(),
        }

    def scope(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "telemetry_scope": "instance",
            "storage": "memory",
            "restart_behavior": "counters and audit reset",
            "audit_capacity": self.audit_limit,
            "global_budget_coordination": False,
        }

    def _rollover(self, day: str) -> None:
        if day == self._day:
            return
        self._day = day
        self._budgets = {
            key: value
            for key, value in self._budgets.items()
            if key[0] == day or self._daily_inflight[key]
        }

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Accounting instance is closed")

    def close(self) -> None:
        with self._lock:
            self._closed = True
