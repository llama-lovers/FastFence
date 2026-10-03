"""Real adapter and engine composition with explicitly mocked inference responses."""

from __future__ import annotations

import httpx
import pytest

from fastfence.modules.control.domain.models import ToolCall
from tests.fixtures.policy import configure_policy


@pytest.mark.parametrize("category", ["benign", "suspicious", "malicious"])
async def test_real_adapter_severity_controls_strictness_without_changing_other_guards(
    app, tokens, monkeypatch, category
):
    engine = app.state.engine
    configure_policy(
        engine,
        lambda data: data["semantic"].update(
            provider="ollama", threshold=0.5, scan_output=False
        ),
    )

    def respond(request):
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"severity":"' + category + '"}'},
                "done_reason": "stop",
                "prompt_eval_count": 40,
                "eval_count": 5,
            },
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    actor = app.state.identities.authenticate(tokens["analyst-blue"])
    call = ToolCall(
        tool="knowledge.search", arguments={"query": "ordinary request"}
    )
    strict = await engine.invoke(actor, call)
    configure_policy(
        engine, lambda data: data["semantic"].update(threshold=0.8)
    )
    relaxed = await engine.invoke(actor, call)
    assert strict.decision == ("allowed" if category == "benign" else "blocked")
    assert relaxed.decision == (
        "blocked" if category == "malicious" else "allowed"
    )
    assert strict.upstream_executed == (category == "benign")
    assert relaxed.upstream_executed == (category != "malicious")
    assert engine.ledger.stats()["semantic_calls"] == 2
    assert relaxed.policy_version > strict.policy_version
