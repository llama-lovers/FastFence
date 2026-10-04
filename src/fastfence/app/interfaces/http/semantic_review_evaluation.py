"""Semantic-only comparison; never invoke business tools, models or budgets."""

import asyncio
import time

from fastfence.app.interfaces.http.semantic_review_models import (
    RuleCase,
    SemanticOutcome,
)
from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.domain.exceptions import (
    ModelCapacityExceededError,
)
from fastfence.modules.control.domain.models import Policy, SemanticConfig
from fastfence.modules.control.domain.semantic_rules import SemanticRule


def candidate_policy(base: Policy, rule: SemanticRule) -> Policy:
    current = base.semantic
    semantic = current.model_dump(mode="json")
    rules = [item for item in current.rules if item.id != rule.id] + [rule]
    semantic.update(
        provider="laya", rules=[item.model_dump() for item in rules]
    )
    if current.provider != "laya":
        semantic.update(
            model="qwen3:4b", timeout_ms=max(current.timeout_ms, 30_000)
        )
    if rule.direction != "input":
        semantic["scan_output"] = True
    config = SemanticConfig.model_validate(semantic)
    values = base.editable()
    values.update(
        version=base.version + 1, semantic=config.model_dump(mode="json")
    )
    return Policy.model_validate(values)


async def evaluate_case(
    runtime: ControlRuntime, policy: Policy, case: RuleCase
) -> SemanticOutcome:
    config = policy.semantic.scoped(case.direction, case.target)
    if config.provider == "disabled":
        return SemanticOutcome(
            status="not_evaluated", reason="semantic_disabled"
        )
    if case.direction == "output" and not config.scan_output:
        return SemanticOutcome(
            status="not_evaluated", reason="output_scan_disabled"
        )
    started = time.monotonic()
    runtime.ledger.record_semantic_call()
    try:
        async with asyncio.timeout(config.timeout_ms / 1000):
            assessment = await runtime.engine.scanner.assess(case.text, config)
        return SemanticOutcome(
            status="evaluated",
            decision=(
                "blocked"
                if assessment.score >= config.threshold
                else "no_semantic_block"
            ),
            semantic_score=assessment.score,
            latency_ms=elapsed(started),
        )
    except ModelCapacityExceededError:
        reason = "model_capacity_exceeded"
    except TimeoutError:
        reason = "assessment_timeout"
    except Exception:
        reason = "model_unavailable_fail_closed"
    return SemanticOutcome(
        status="error", reason=reason, latency_ms=elapsed(started)
    )


def elapsed(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))
