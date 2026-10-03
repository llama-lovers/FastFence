"""Real Engine and crypto enforce semantic policies on restored visible text."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from fastfence.modules.anonymization.application.facade import (
    AnonymizationRuntime,
)
from fastfence.modules.control.application.services.engine import Engine
from fastfence.modules.control.domain.models import (
    Assessment,
    Identity,
    ModelCall,
    ToolCall,
)
from fastfence.modules.control.persistence.ledger import Ledger
from fastfence.modules.control.persistence.policy import PolicyStore
from tests.fixtures.policy import configure_policy


@pytest.fixture
def runtime(configuration):
    scanner = Mock(assess=AsyncMock(return_value=Assessment(score=0, tokens=7)))
    models = Mock(
        complete=AsyncMock(return_value=({"text": "ProjectHazel"}, 10))
    )
    tools = Mock(
        supports=Mock(return_value=True),
        validate=Mock(side_effect=lambda _name, payload, _identity: payload),
        call=AsyncMock(return_value={"text": "ProjectHazel"}),
    )
    ledger = Ledger(instance_id="restoration-regression")
    ledger.reserve = Mock(wraps=ledger.reserve)
    engine = Engine(
        policies=PolicyStore(*configuration),
        ledger=ledger,
        tools=tools,
        scanner=scanner,
        models=models,
        anonymization=AnonymizationRuntime(
            keyring={"test": bytes(range(32))}, current_key_id="test"
        ),
    )

    def enable(data):
        data["semantic"].update(
            provider="laya",
            timeout_ms=100,
            rules=[
                {
                    "id": "classified-project",
                    "instruction": "Never reveal the classified name ProjectHazel.",
                    "direction": "output",
                }
            ],
        )
        data["anonymization"] = {
            "enabled": True,
            "mode": "reversible",
            "rules": [
                {
                    "id": "project",
                    "operator": "literal",
                    "value": "ProjectHazel",
                    "replacement": "PROJECT",
                    "allow_restore": True,
                }
            ],
        }

    configure_policy(engine, enable)
    yield engine
    ledger.close()


def invocation(target="model", restore=True):
    if target == "tool":
        return ToolCall(
            tool="knowledge.search",
            arguments={"query": "Hello"},
            restore_originals=restore,
        )
    return ModelCall(
        model="qwen3:0.6b",
        prompt="Hello",
        max_output_tokens=16,
        restore_originals=restore,
    )


async def invoke(engine, call):
    return await engine.invoke(
        Identity(subject="reader", tenant="test", roles=["analyst"]), call
    )


@pytest.mark.parametrize("target", ["model", "tool"])
async def test_restored_original_cannot_bypass_named_semantic_rule(
    runtime, target
):
    seen = []

    async def assess(text, config):
        seen.append(text)
        return Assessment(
            score=int(bool(config.rules) and "ProjectHazel" in text), tokens=7
        )

    runtime.scanner.assess.side_effect = assess
    verdict = await invoke(runtime, invocation(target))
    assert verdict.reason == "semantic_output_risk"
    assert verdict.semantic_input_status == "passed"
    assert verdict.semantic_output_status == "blocked"
    assert verdict.upstream_executed and verdict.output is None
    assert len(seen) == 3
    assert "ProjectHazel" not in seen[1] and "FFR1." in seen[1]
    assert "ProjectHazel" in seen[2]
    assert "ProjectHazel" not in json.dumps(runtime.ledger.audit())
    # The third assessment was charged even though it denied delivery.
    assert verdict.tokens >= 3 * 7


async def test_successful_restoration_reserves_extra_tokens_and_compute(
    runtime,
):
    masked = await invoke(runtime, invocation(restore=False))
    ordinary_reserve = runtime.ledger.reserve.call_args.args
    restored = await invoke(runtime, invocation())
    restoration_reserve = runtime.ledger.reserve.call_args.args
    config = runtime.policies.snapshot().policy
    assert restored.output == {"text": "ProjectHazel"}
    assert restored.restored and restored.semantic_output_status == "passed"
    assert runtime.scanner.assess.await_count == 5
    assert restored.tokens == masked.tokens + 7
    assert (
        restoration_reserve[3] - ordinary_reserve[3]
        == config.max_output_bytes + config.semantic.token_allowance
    )
    assert (
        restoration_reserve[5] - ordinary_reserve[5]
        == config.semantic.timeout_ms
    )


@pytest.mark.parametrize(
    "limit,reason",
    [("tokens", "budget_tokens"), ("compute_ms", "budget_compute_ms")],
)
async def test_extra_assessment_must_fit_budget_before_any_provider(
    runtime, limit, reason
):
    await invoke(runtime, invocation(restore=False))
    reservation = runtime.ledger.reserve.call_args.args
    maximum = reservation[3 if limit == "tokens" else 5]
    runtime.ledger.close()
    runtime.ledger = Ledger(instance_id="fresh-limited")
    configure_policy(
        runtime,
        lambda data: data["budgets"]["analyst"].update({limit: maximum}),
    )
    runtime.scanner.assess.reset_mock()
    runtime.models.complete.reset_mock()
    verdict = await invoke(runtime, invocation())
    assert verdict.reason == reason and not verdict.upstream_executed
    runtime.scanner.assess.assert_not_awaited()
    runtime.models.complete.assert_not_awaited()


@pytest.mark.parametrize("failure", ["error", "timeout", "cancel", "usage"])
async def test_failed_restoration_scan_never_releases_text_and_settles(
    runtime, failure
):
    calls = 0

    async def assess(_text, _config):
        nonlocal calls
        calls += 1
        if calls == 3:
            if failure == "error":
                raise RuntimeError("synthetic provider error")
            if failure == "timeout":
                await asyncio.Event().wait()
            if failure == "cancel":
                raise asyncio.CancelledError
            if failure == "usage":
                return Assessment(score=0, tokens=1_000_000)
        return Assessment(score=0, tokens=7)

    runtime.scanner.assess.side_effect = assess
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await invoke(runtime, invocation())
        verdict = runtime.ledger.audit()[0]
        assert verdict["reason"] == "request_cancelled"
    else:
        result = await invoke(runtime, invocation())
        assert result.output is None
        assert (
            result.reason
            == {
                "error": "upstream_failure",
                "timeout": "upstream_timeout",
                "usage": "semantic_usage_exceeded",
            }[failure]
        )
        verdict = result.model_dump()
    assert verdict["semantic_output_status"] == "error"
    assert not runtime.ledger._reservations
    assert "ProjectHazel" not in json.dumps(runtime.ledger.audit())


async def test_unchanged_output_skips_extra_scan(runtime):
    runtime.models.complete.return_value = ({"text": "Hello"}, 10)
    verdict = await invoke(runtime, invocation())
    assert verdict.output == {"text": "Hello"} and not verdict.restored
    assert runtime.scanner.assess.await_count == 2
