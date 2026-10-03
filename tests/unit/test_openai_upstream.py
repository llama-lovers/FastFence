"""Untrusted provider replies cannot bypass text and accounting contracts."""

import copy
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import ModelMessage
from fastfence.modules.control.persistence.openai_models import OpenAIModels
from fastfence.shared.settings.app_settings import AppSettings


def completion():
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 2,
            "total_tokens": 14,
        },
    }


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    options = []

    def client(**kwargs):
        options.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return options


async def test_transport_preserves_messages_and_protects_upstream_key(
    monkeypatch,
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=completion())

    options = install_transport(monkeypatch, handler)
    key = SecretStr("synthetic-provider-credential")
    adapter = OpenAIModels("https://models.example.test/v1/", key)
    messages = [
        ModelMessage(role="system", content="Be concise"),
        ModelMessage(role="user", content="Hi"),
    ]
    result, tokens = await adapter.complete(
        "allowed-model", "", 20, 1000, stop=["END"], messages=messages
    )
    assert result == {
        "text": "Hello",
        "model": "allowed-model",
        "finish_reason": "stop",
    }
    assert tokens == 14
    assert (
        str(requests[0].url)
        == "https://models.example.test/v1/chat/completions"
    )
    body = json.loads(requests[0].content)
    assert body["messages"] == [message.model_dump() for message in messages]
    assert (
        body["stream"] is False
        and body["max_tokens"] == 20
        and body["stop"] == ["END"]
    )
    assert (
        requests[0].headers["Authorization"]
        == "Bearer " + key.get_secret_value()
    )
    assert "synthetic-provider-credential" not in repr(adapter)
    assert options[0]["trust_env"] is options[0]["follow_redirects"] is False


@pytest.mark.parametrize(
    "mode",
    [
        "no_usage",
        "boolean_usage",
        "negative_usage",
        "excess_usage",
        "wrong_total",
        "no_finish",
        "null_finish",
        "tool_finish",
        "tool_calls",
        "function_call",
        "refusal",
        "nontext",
        "two_choices",
        "duplicate",
        "huge",
        "encoded",
        "redirect",
        "timeout",
    ],
)
async def test_provider_failures_are_sanitized(monkeypatch, mode):
    data = copy.deepcopy(completion())
    choice = data["choices"][0]
    mutations = {
        "no_usage": lambda: data.pop("usage"),
        "boolean_usage": lambda: data["usage"].update(prompt_tokens=True),
        "negative_usage": lambda: data["usage"].update(prompt_tokens=-1),
        "excess_usage": lambda: data["usage"].update(
            completion_tokens=21, total_tokens=33
        ),
        "wrong_total": lambda: data["usage"].update(total_tokens=0),
        "no_finish": lambda: choice.pop("finish_reason"),
        "null_finish": lambda: choice.update(finish_reason=None),
        "tool_finish": lambda: choice.update(finish_reason="tool_calls"),
        "tool_calls": lambda: choice["message"].update(tool_calls=[{}]),
        "function_call": lambda: choice["message"].update(function_call={}),
        "refusal": lambda: choice["message"].update(refusal="private reason"),
        "nontext": lambda: choice["message"].update(
            content=[{"text": "unsafe mode"}]
        ),
        "two_choices": lambda: data.update(choices=[choice, choice]),
    }
    if mode in mutations:
        mutations[mode]()

    def handler(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("PRIVATE_PROVIDER_DETAIL")
        if mode == "redirect":
            return httpx.Response(
                307, headers={"location": "https://elsewhere.example/"}
            )
        if mode == "duplicate":
            return httpx.Response(200, content=b'{"choices":[],"choices":[]}')
        if mode == "huge":
            return httpx.Response(200, content=b"x" * 262145)
        if mode == "encoded":
            return httpx.Response(
                200, content=b"{}", headers={"content-encoding": "custom"}
            )
        return httpx.Response(200, json=data)

    install_transport(monkeypatch, handler)
    with pytest.raises(ModelUnavailableError) as error:
        await OpenAIModels("http://127.0.0.1:1234/v1").complete(
            "test", "PRIVATE_PROMPT", 20, 1000
        )
    assert str(error.value) == "Model unavailable or invalid response"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/v1",
        "https://user:secret@example.test/v1",  # pragma: allowlist secret
        "https://example.test/v1?key=secret",
        "https://example.test/v1#fragment",
        "file:///tmp/models",
        "http://127.0.0.1:0/v1",
        "https://example.test:99999/v1",
        "https://example.test/\n",
        "http://192.168.0.1/v1",
    ],
)
def test_unsafe_urls_rejected_at_settings_boundary(url):
    with pytest.raises(ValidationError):
        AppSettings(openai_base_url=url)


def test_secret_not_exposed_and_loopback_ipv6_supported():
    settings = AppSettings(
        model_provider="openai",
        openai_base_url="http://[::1]:8080/v1/",
        openai_api_key="synthetic-provider-credential",  # pragma: allowlist secret
    )
    assert settings.openai_base_url == "http://[::1]:8080/v1"
    assert (
        "synthetic-provider-credential"
        not in repr(settings) + settings.model_dump_json()
    )


def test_runtime_selects_openai_without_switching_scanner(project):
    from fastfence.modules.control.application.facade import build_runtime

    runtime = build_runtime(
        AppSettings(
            root=project,
            model_provider="openai",
            openai_base_url="https://models.example.test/v1",
            ollama_url="http://127.0.0.1:11434",
        )
    )
    try:
        assert isinstance(runtime.engine.models, OpenAIModels)
        assert runtime.engine.scanner.ollama_url == "http://127.0.0.1:11434"
    finally:
        runtime.close()
