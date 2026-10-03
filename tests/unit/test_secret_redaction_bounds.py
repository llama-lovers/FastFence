"""Redaction expansion must preserve configured input/output byte limits."""

from fastfence.modules.control.application.services.inspection import encode
from fastfence.modules.control.domain.models import ToolCall
from tests.fixtures.policy import configure_policy


async def test_expanded_input_is_denied_before_upstream(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    configure_policy(
        engine,
        lambda data: data.update(
            privacy={"enabled": True, "input": "redact", "output": "redact"},
            max_input_bytes=64,
        ),
    )
    attempted = []

    async def upstream(*args):
        attempted.append(args)
        return {"message": "ordinary output"}

    monkeypatch.setattr(engine.tools, "call", upstream)
    arguments = {"query": "password='1' " * 3}
    assert len(encode(arguments).encode()) <= 64
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    result = await engine.invoke(
        identity, ToolCall(tool="knowledge.search", arguments=arguments)
    )
    assert result.decision == "blocked" and result.reason == "input_too_large"
    assert "detect_secrets_KeywordDetector" in result.findings
    assert not attempted and not result.upstream_executed
    assert result.output is None and engine.ledger.budgets() == []


async def test_expanded_output_is_not_delivered_after_upstream(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    configure_policy(
        engine,
        lambda data: data.update(max_output_bytes=64),
    )
    output = {"message": "password='1' " * 3}
    assert len(encode(output).encode()) <= 64
    attempted = []

    async def upstream(*args):
        attempted.append(args)
        return output

    monkeypatch.setattr(engine.tools, "call", upstream)
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    result = await engine.invoke(
        identity,
        ToolCall(tool="knowledge.search", arguments={"query": "forecast"}),
    )
    assert result.decision == "blocked" and result.reason == "output_too_large"
    assert "detect_secrets_KeywordDetector" in result.findings
    assert len(attempted) == 1 and result.upstream_executed
    assert result.output is None
