"""Actual protected ACP tool path distinguishes rejected and attempted work."""

import httpx
import pytest

from fastfence.modules.control.domain.models import Assessment
from fastfence.modules.control.persistence.acp_tools import ACPTools
from fastfence.modules.control.persistence.model_http import (
    MAX_PENDING_REQUESTS,
)
from fastfence.shared.acp import ACPAgentSettings
from tests.fixtures.auth import headers
from tests.fixtures.policy import configure_policy


def configure(app, semantic=False):
    tools = ACPTools(
        {
            "peer": ACPAgentSettings(
                base_url="https://peer.test", agent_name="remote"
            )
        }
    )
    app.state.engine.tools = tools

    def policy(data):
        data["tools"]["acp.peer"] = {
            "roles": ["analyst"],
            "timeout_ms": 1000,
            "cost_microusd": 123,
        }
        if semantic:
            data["semantic"]["provider"] = "laya"

    configure_policy(app.state.engine, policy)
    return tools


def invoke(client, tokens):
    return client.post(
        "/api/invoke",
        headers=headers(tokens),
        json={
            "tool": "acp.peer",
            "arguments": {"input": [{"role": 0, "parts": ["hello"]}]},
        },
    )


@pytest.mark.parametrize("semantic", [False, True])
def test_pre_admission_rejects_without_false_upstream_or_cost(
    client, app, tokens, monkeypatch, semantic
):
    tools = configure(app, semantic)
    tools._http._pending = MAX_PENDING_REQUESTS

    async def assessed(*_):
        return Assessment(score=0, tokens=10)

    monkeypatch.setattr(app.state.engine.scanner, "assess", assessed)
    result = invoke(client, tokens)
    tools._http._pending = 0
    assert result.status_code == 200
    verdict = result.json()
    assert verdict["reason"] == "tool_capacity_exceeded"
    assert verdict["decision"] == "error" and not verdict["upstream_executed"]
    assert verdict["cost_microusd"] == 0
    assert tools._http._client is None
    assert verdict["semantic_input_status"] == (
        "passed" if semantic else "not_run"
    )
    budget = app.state.engine.ledger.budgets()[0]
    assert budget["inflight"] == 0 and budget["calls"] == 1
    assert budget["tokens"] == verdict["tokens"] > 0
    assert budget["cost_microusd"] == 0


@pytest.mark.parametrize("status", [429, 503])
def test_remote_overload_remains_attempted_conservative_failure(
    client, app, tokens, monkeypatch, status
):
    tools = configure(app)
    original = httpx.AsyncClient
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"Retry-After": "10"}, text="PRIVATE_REMOTE_ERROR"
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(provider), **kwargs
        ),
    )
    result = invoke(client, tokens)
    verdict = result.json()
    assert (
        verdict["decision"] == "error"
        and verdict["reason"] == "upstream_failure"
    )
    assert verdict["upstream_executed"] and verdict["cost_microusd"] == 123
    assert len(calls) == 1 and tools._http._pending == 0
    assert "PRIVATE_REMOTE_ERROR" not in result.text
    assert "Retry-After" not in result.headers
    budget = app.state.engine.ledger.budgets()[0]
    assert budget["inflight"] == 0 and budget["cost_microusd"] == 123
    assert budget["tokens"] == verdict["tokens"] > 1000
