"""Read-only, bounded evaluation of a candidate named rule by actual Laya."""

import asyncio
import time
from typing import Any, Literal

from fastfence.modules.control.application.services.engine import Engine
from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.modules.control.domain.semantic_rules import SemanticRule


async def preview_semantic(
    engine: Engine,
    rule: SemanticRule,
    text: str,
    direction: Literal["input", "output"],
    target: Literal["model", "tool"],
    base_version: int,
) -> dict[str, Any]:
    snapshot = engine.policies.snapshot()
    if snapshot.policy.version != base_version:
        raise ValueError(
            "Policy changed. Refresh and test against the active version."
        )
    current = snapshot.policy.semantic
    values = current.model_dump(mode="json")
    existing = list(current.rules)
    rules = [item for item in existing if item.id != rule.id] + [rule]
    values.update(provider="laya", rules=[item.model_dump() for item in rules])
    if current.provider != "laya":
        values.update(
            model="qwen3:4b", timeout_ms=max(current.timeout_ms, 30_000)
        )
    if rule.direction != "input":
        values["scan_output"] = True
    config = SemanticConfig.model_validate(values).scoped(direction, target)
    started = time.perf_counter()
    engine.ledger.record_semantic_call()
    async with asyncio.timeout(config.timeout_ms / 1000):
        assessment = await engine.scanner.assess(text, config)
    return {
        "decision": "blocked"
        if assessment.score >= config.threshold
        else "no_semantic_block",
        "semantic_score": assessment.score,
        "provider": "laya",
        "model": config.model,
        "rule_applied": rule.applies_to(direction, target),
        "base_version": base_version,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }
