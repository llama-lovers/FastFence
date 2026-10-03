"""Named semantic policies retain explicit scope and bounded model context."""

from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from fastfence.modules.control.application.services.execution import Executor
from fastfence.modules.control.domain.models import (
    Assessment,
    Identity,
    InvocationState,
    ModelCall,
    Policy,
    SemanticConfig,
    SignatureFeed,
    Snapshot,
    ToolCall,
    Verdict,
)
from fastfence.modules.control.domain.semantic_rules import SemanticRule


def rule(**changes):
    return SemanticRule.model_validate(
        {
            "id": "named",
            "instruction": "Block personalized financial advice",
            **changes,
        }
    )


def test_named_rules_require_laya_and_unique_ids():
    with pytest.raises(ValidationError, match="require Laya"):
        SemanticConfig(provider="ollama", rules=(rule(),))
    with pytest.raises(ValidationError, match="unique"):
        SemanticConfig(provider="laya", rules=(rule(), rule()))
    with pytest.raises(ValidationError, match="blank"):
        rule(instruction=" \n ")
    with pytest.raises(ValidationError, match="output scanning"):
        SemanticConfig(provider="laya", scan_output=False, rules=(rule(),))


def test_semantic_rule_context_is_utf8_bounded_and_fully_reserved():
    config = SemanticConfig(
        provider="laya", rules=(rule(instruction="ą" * 2048),)
    )
    assert config.token_allowance == 2048 + len(config.policy_text.encode())
    with pytest.raises(ValidationError, match="8192 UTF-8"):
        SemanticConfig(
            provider="laya",
            instructions="ą" * 2048,
            rules=(rule(instruction="ą" * 2048),),
        )
    with pytest.raises(ValidationError):
        SemanticConfig(
            provider="laya", rules=tuple(rule(id=f"r{i}") for i in range(9))
        )


@pytest.mark.parametrize(
    "direction,target,expected",
    [
        ("input", "model", ["model-input", "global"]),
        ("output", "model", ["global"]),
        ("input", "tool", ["global"]),
        ("output", "tool", ["tool-output", "global"]),
    ],
)
def test_filter_preserves_global_instructions_and_exact_scope(
    direction, target, expected
):
    config = SemanticConfig(
        provider="laya",
        instructions="Global instruction",
        rules=(
            rule(id="model-input", direction="input", target="model"),
            rule(id="tool-output", direction="output", target="tool"),
            rule(id="global"),
        ),
    )
    effective = config.scoped(direction, target)
    assert [item.id for item in effective.rules] == expected
    assert effective.instructions == config.instructions
    assert len(config.rules) == 3


@pytest.mark.parametrize(
    "direction,is_tool,expected",
    [
        ("input", False, ["model-input"]),
        ("output", False, []),
        ("input", True, []),
        ("output", True, ["tool-output"]),
    ],
)
async def test_executor_makes_one_assessment_with_only_applicable_rules(
    direction, is_tool, expected
):
    config = SemanticConfig(
        provider="laya",
        rules=(
            rule(id="model-input", direction="input", target="model"),
            rule(id="tool-output", direction="output", target="tool"),
        ),
    )
    state = InvocationState(
        identity=Identity(
            subject="subject", tenant="tenant", roles=["analyst"]
        ),
        call=ToolCall(tool="fixture.tool")
        if is_tool
        else ModelCall(model="test", prompt="Hello"),
        snapshot=Snapshot(
            policy=Policy(
                version=1,
                description="test",
                tools={},
                budgets={},
                semantic=config,
            ),
            feed=SignatureFeed(version=1, signatures=[]),
        ),
        verdict=Verdict(
            request_id="test",
            decision="allowed",
            reason="test",
            policy_version=1,
            feed_version=1,
            latency_ms=0,
            semantic_provider="laya",
        ),
        started_at=0,
        target="test",
    )
    scanner = Mock(assess=AsyncMock(return_value=Assessment(score=0, tokens=1)))
    executor = Executor(
        ledger=Mock(),
        scanner=scanner,
        tools=Mock(),
        models=Mock(),
        secrets=Mock(),
        anonymization=None,
    )
    await executor.scan(state, "Hello", config.token_allowance + 5, direction)
    scanner.assess.assert_awaited_once()
    effective = scanner.assess.call_args.args[1]
    assert [item.id for item in effective.rules] == expected
    assert getattr(state.verdict, f"semantic_{direction}_status") == "passed"
