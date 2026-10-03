"""Provider prompt-template overhead must be reserved before a model request."""

import json

import httpx

from fastfence.modules.control.application.services.inspection import encode
from fastfence.modules.control.domain.models import Assessment, ModelCall
from tests.fixtures.policy import configure_policy


async def test_short_real_adapter_usage_is_allowed_and_unused_allowance_released(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    reserved = []

    def respond(request):
        body = json.loads(request.content)
        assert body["prompt"] == "Hi"
        assert body["options"]["num_predict"] == 1
        reserved.append(engine.ledger.budgets()[0]["tokens"])
        return httpx.Response(
            200,
            json={
                "response": "H",
                "prompt_eval_count": 17,
                "eval_count": 1,
                "done_reason": "length",
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
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    result = await engine.invoke(
        identity,
        ModelCall(model="qwen3:0.6b", prompt="Hi", max_output_tokens=1),
    )
    assert reserved == [1040]
    assert result.decision == "allowed" and result.upstream_executed
    assert result.tokens == engine.ledger.budgets()[0]["tokens"] == 18
    assert result.output["finish_reason"] == "length"
    assert engine.ledger.budgets()[0]["inflight"] == 0


async def test_full_template_reservation_is_required_before_upstream(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    configure_policy(
        engine, lambda data: data["budgets"]["analyst"].update(tokens=1039)
    )
    attempted = []

    async def complete(*args, **kwargs):
        attempted.append((args, kwargs))
        return {"text": "H"}, 18

    monkeypatch.setattr(engine.models, "complete", complete)
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    result = await engine.invoke(
        identity,
        ModelCall(model="qwen3:0.6b", prompt="Hi", max_output_tokens=1),
    )
    assert result.decision == "blocked" and result.reason == "budget_tokens"
    assert not result.upstream_executed and not attempted
    assert result.tokens == 0 and engine.ledger.budgets() == []


async def test_excess_provider_usage_blocks_delivery_and_retains_bounded_charge(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    configure_policy(
        engine, lambda data: data["budgets"]["analyst"].update(tokens=1040)
    )
    attempted = []

    async def complete(*args, **kwargs):
        attempted.append((args, kwargs))
        return {"text": "H"}, 1041

    monkeypatch.setattr(engine.models, "complete", complete)
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    call = ModelCall(model="qwen3:0.6b", prompt="Hi", max_output_tokens=1)
    result = await engine.invoke(identity, call)
    assert (
        result.decision == "blocked" and result.reason == "model_usage_exceeded"
    )
    assert result.upstream_executed and result.output is None
    row = engine.ledger.budgets()[0]
    assert result.tokens == row["tokens"] == 1040 and row["inflight"] == 0
    subsequent = await engine.invoke(identity, call)
    assert subsequent.reason == "budget_tokens" and len(attempted) == 1


async def test_semantic_reservations_remain_independent_of_model_template_allowance(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    configure_policy(
        engine, lambda data: data["semantic"].update(provider="ollama")
    )
    reserved = []
    scans = []

    async def assess(text, config):
        scans.append(text)
        return Assessment(score=0, tokens=len(text.encode()) + 1024)

    async def complete(*args, **kwargs):
        reserved.append(engine.ledger.budgets()[0]["tokens"])
        return {"text": "H"}, 18

    monkeypatch.setattr(engine.scanner, "assess", assess)
    monkeypatch.setattr(engine.models, "complete", complete)
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    result = await engine.invoke(
        identity,
        ModelCall(model="qwen3:0.6b", prompt="Hi", max_output_tokens=1),
    )
    semantic_allocation = 15 + 2048 + 16_384 + 2048
    assert reserved == [1040 + semantic_allocation]
    assert result.decision == "allowed" and len(scans) == 2
    expected_charge = 18 + sum(len(text.encode()) + 1024 for text in scans)
    assert (
        result.tokens == engine.ledger.budgets()[0]["tokens"] == expected_charge
    )
    assert len(encode({"prompt": "Hi"}).encode()) == 15
