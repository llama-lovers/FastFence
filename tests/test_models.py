from __future__ import annotations

import json

import httpx
import pytest

from fastfence.adapters.models import ModelUnavailable, OllamaModels, SemanticScanner
from fastfence.core.schema import SemanticConfig


@pytest.mark.parametrize("provider", ["ollama", "kev"])
async def test_real_adapter_wire_contract(monkeypatch, provider):
    captured = {}

    def respond(request):
        captured.update(json.loads(request.content))
        if provider == "ollama":
            return httpx.Response(
                200,
                json={
                    "message": {"content": '{"risk":0.87}'},
                    "prompt_eval_count": 80,
                    "eval_count": 9,
                },
            )
        return httpx.Response(
            200,
            json={
                "answers": {"risk": {"type": "noul", "noul": 0.87}},
                "usage": {"input_tokens": 80, "output_tokens": 9},
            },
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs),
    )
    assessment = await SemanticScanner("http://local", "http://local").assess(
        "untrusted content", SemanticConfig(provider=provider)
    )
    assert assessment.score == 0.87 and assessment.tokens > 0
    if provider == "ollama":
        assert captured["think"] is False and captured["stream"] is False
        assert captured["options"]["num_predict"] == 256
    else:
        assert captured["questions"]["risk"]["type"] == "noul"
        assert captured["state"] == "untrusted content"


@pytest.mark.parametrize("risk", [-1, 2, "safe", True, None, float("nan")])
async def test_invalid_classifier_scores_fail_closed(monkeypatch, risk):
    def respond(request):
        return httpx.Response(200, json={"message": {"content": json.dumps({"risk": risk})}})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs),
    )
    with pytest.raises(ModelUnavailable):
        await SemanticScanner("http://local", "http://local").assess(
            "text", SemanticConfig(provider="ollama")
        )


async def test_completion_enforces_output_token_bound(monkeypatch):
    def respond(request):
        assert json.loads(request.content)["options"]["num_predict"] == 12
        return httpx.Response(
            200, json={"response": "safe", "prompt_eval_count": 3, "eval_count": 20}
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs),
    )
    with pytest.raises(ModelUnavailable):
        await OllamaModels("http://local").complete("allowed-model", "safe", 12, 1000)
