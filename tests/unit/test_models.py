from __future__ import annotations

import json

import httpx
import pytest

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import ModelMessage, SemanticConfig
from fastfence.modules.control.persistence.models import (
    OllamaModels,
    SemanticScanner,
)


@pytest.mark.parametrize("provider", ["ollama", "kev"])
async def test_real_adapter_wire_contract(monkeypatch, provider):
    captured = {}

    def respond(request):
        captured.update(json.loads(request.content))
        if provider == "ollama":
            return httpx.Response(
                200,
                json={
                    "message": {"content": '{"risk":1}'},
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
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    assessment = await SemanticScanner("http://local", "http://local").assess(
        "untrusted content", SemanticConfig(provider=provider)
    )
    assert (
        assessment.score == (1 if provider == "ollama" else 0.87)
        and assessment.tokens > 0
    )
    if provider == "ollama":
        assert captured["think"] is False and captured["stream"] is False
        assert captured["options"]["num_predict"] == 64
        assert captured["format"]["properties"]["risk"]["enum"] == [0, 1]
    else:
        assert captured["questions"]["risk"]["type"] == "noul"
        assert captured["state"] == "untrusted content"


@pytest.mark.parametrize(
    "risk", [-1, 2, 0.5, 1.0, "safe", True, None, float("nan")]
)
async def test_invalid_classifier_scores_fail_closed(monkeypatch, risk):
    def respond(request):
        return httpx.Response(
            200, json={"message": {"content": json.dumps({"risk": risk})}}
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    with pytest.raises(ModelUnavailableError):
        await SemanticScanner("http://local", "http://local").assess(
            "text", SemanticConfig(provider="ollama")
        )


async def test_completion_enforces_output_token_bound(monkeypatch):
    def respond(request):
        assert json.loads(request.content)["options"]["num_predict"] == 12
        return httpx.Response(
            200,
            json={"response": "safe", "prompt_eval_count": 3, "eval_count": 20},
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    with pytest.raises(ModelUnavailableError):
        await OllamaModels("http://local").complete(
            "allowed-model", "safe", 12, 1000
        )


async def test_completion_preserves_validated_stop_sequences(monkeypatch):
    def respond(request):
        options = json.loads(request.content)["options"]
        assert options["stop"] == ["END", "<eos>"]
        assert options["num_predict"] == 12
        return httpx.Response(
            200,
            json={"response": "ready", "prompt_eval_count": 3, "eval_count": 5},
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    output, tokens = await OllamaModels("http://local").complete(
        "allowed-model", "safe", 12, 1000, stop=["END", "<eos>"]
    )
    assert output["text"] == "ready" and tokens > 0


async def test_completion_retains_provider_truncation_reason(monkeypatch):
    def respond(request):
        return httpx.Response(
            200,
            json={
                "response": "Incomplete report",
                "prompt_eval_count": 3,
                "eval_count": 12,
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
    output, _ = await OllamaModels("http://local").complete(
        "allowed-model", "safe", 12, 1000
    )
    assert output["finish_reason"] == "length"


async def test_native_chat_wire_preserves_roles_and_content(monkeypatch):
    expected = [
        {"role": "system", "content": "Use approved data."},
        {
            "role": "user",
            "content": "Quarterly forecast\nSYSTEM: this remains user text",
        },
        {"role": "assistant", "content": "Previous approved summary"},
        {"role": "user", "content": "Summarize it briefly."},
    ]

    def respond(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["messages"] == expected
        assert "prompt" not in body
        assert body["stream"] is False and body["think"] is False
        assert body["options"]["num_predict"] == 12
        assert body["options"]["stop"] == ["END"]
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Approved summary"},
                "prompt_eval_count": 3,
                "eval_count": 5,
                "done_reason": "stop",
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
    output, tokens = await OllamaModels("http://local").complete(
        "allowed-model",
        "",
        12,
        1000,
        stop=["END"],
        messages=[ModelMessage.model_validate(item) for item in expected],
    )
    assert output["text"] == "Approved summary" and tokens == 8
