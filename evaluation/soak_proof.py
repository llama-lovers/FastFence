"""Independent per-snapshot outcome and retained-audit/settlement invariants."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Generation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_version: int = Field(ge=1)
    feed_version: int = Field(ge=1)
    input_action: Literal["block", "redact"]
    dynamic_signature: bool

    def expected(self, case: str) -> tuple[str, str, bool]:
        fixed = {
            "allowed": ("allowed", "controls_passed", True),
            "signature": ("blocked", "attack_signature", False),
            "rbac": ("blocked", "role_not_allowed", False),
            "output_redaction": ("redacted", "privacy_redacted", True),
        }
        if case == "sensitive_input":
            return (
                ("blocked", "input_sensitive_data", False)
                if self.input_action == "block"
                else ("redacted", "privacy_redacted", True)
            )
        if case == "dynamic_signature":
            return (
                ("blocked", "attack_signature", False)
                if self.dynamic_signature
                else fixed["allowed"]
            )
        return fixed[case]


class SoakProof(BaseModel):
    generations: dict[tuple[int, int], Generation] = Field(default_factory=dict)
    records: dict[str, tuple[int, int, str, str, bool]] = Field(
        default_factory=dict
    )
    decisions: dict[str, int] = Field(default_factory=dict)
    workloads: dict[str, int] = Field(default_factory=dict)
    protocols: dict[str, int] = Field(default_factory=dict)
    observed_generations: set[tuple[int, int]] = Field(default_factory=set)
    coverage: set[tuple[int, int, str, str]] = Field(default_factory=set)
    calls: int = 0
    tokens: int = 0
    cost: int = 0

    def register(self, generation: Generation) -> None:
        key = (generation.policy_version, generation.feed_version)
        if key in self.generations and self.generations[key] != generation:
            raise ValueError("Conflicting expected generation")
        self.generations[key] = generation

    def record(self, verdict: dict[str, Any], case: str, protocol: str) -> None:
        if len(self.records) >= 200_000:
            raise ValueError("Soak client record bound exceeded")
        pair = (verdict["policy_version"], verdict["feed_version"])
        if pair not in self.generations:
            raise ValueError("Unknown or mixed policy/feed snapshot")
        actual = (
            verdict["decision"],
            verdict["reason"],
            verdict["upstream_executed"],
        )
        if actual != self.generations[pair].expected(case) or not isinstance(
            actual[2], bool
        ):
            raise ValueError(f"Unexpected soak outcome: {case}")
        identifier = verdict["request_id"]
        if identifier in self.records:
            raise ValueError("Duplicate invocation identity")
        self.records[identifier] = (*pair, *actual)
        self.observed_generations.add(pair)
        self.coverage.add((*pair, case, protocol))
        for counter, name in [
            (self.decisions, actual[0]),
            (self.workloads, case),
            (self.protocols, protocol),
        ]:
            counter[name] = counter.get(name, 0) + 1
        self.calls += int(actual[2])
        self.tokens += verdict["tokens"]
        self.cost += verdict["cost_microusd"]
        text = str(verdict.get("output", ""))
        if "anna@example.org" in text or "sk-demoOnlySecret123456789" in text:
            raise ValueError("Sensitive output escaped redaction")

    def verify_audit(self, audit: list[dict], retained: int) -> None:
        total = len(self.records)
        sequences = sorted(row["sequence"] for row in audit)
        if sequences != list(range(total - retained + 1, total + 1)):
            raise ValueError(
                "Retained audit sequence is not the final bounded tail"
            )
        for row in audit:
            recorded = (
                row["policy_version"],
                row["feed_version"],
                row["decision"],
                row["reason"],
                row["upstream_executed"],
            )
            if self.records.get(row["request_id"]) != recorded:
                raise ValueError("Audit differs from returned snapshot/verdict")
            if {"prompt", "output", "arguments"}.intersection(row):
                raise ValueError("Audit unexpectedly retains private payload")

    def verify(
        self, status: dict[str, Any], audit: list[dict], capacity: int
    ) -> None:
        total = len(self.records)
        metrics = status["metrics"]
        if (
            metrics["requests"] != total
            or metrics["semantic_calls"]
            or metrics["errors"]
        ):
            raise ValueError(
                "Invocation/semantic/error metrics do not reconcile"
            )
        if any(
            metrics[name] != self.decisions.get(name, 0)
            for name in ["allowed", "blocked", "redacted"]
        ):
            raise ValueError("Decision counters do not reconcile")
        retained = min(total, capacity)
        if (
            metrics["audit_retained"],
            metrics["audit_dropped"],
            metrics["latency_sample_size"],
        ) != (retained, total - retained, min(total, 2048)):
            raise ValueError("Bounded telemetry counts do not reconcile")
        if (
            len(audit) != retained
            or len({row["request_id"] for row in audit}) != retained
        ):
            raise ValueError("Retained audit missing or duplicated")
        self.verify_audit(audit, retained)
        budgets = status["budgets"]
        if len(budgets) != 1 or budgets[0]["subject"] != "analyst-blue":
            raise ValueError("Unexpected accounting identity")
        if tuple(
            budgets[0][key]
            for key in ["calls", "tokens", "cost_microusd", "inflight"]
        ) != (self.calls, self.tokens, self.cost, 0):
            raise ValueError("Budget settlement/reservations do not reconcile")
        if set(self.generations) != self.observed_generations:
            raise ValueError("A published valid generation was not exercised")
        expected_coverage = {
            (*pair, case, protocol)
            for pair in self.generations
            for case in [
                "allowed",
                "signature",
                "sensitive_input",
                "output_redaction",
                "rbac",
                "dynamic_signature",
            ]
            for protocol in ["http", "mcp"]
        }
        if self.coverage != expected_coverage:
            raise ValueError(
                "Each snapshot must exercise every workload through both protocols"
            )
        if set(self.protocols) != {"http", "mcp"} or len(self.workloads) != 6:
            raise ValueError("Missing protocol or workload coverage")
