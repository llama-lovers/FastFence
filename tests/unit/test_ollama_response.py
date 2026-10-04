"""Native non-streaming provider replies require explicit completion and usage."""

import httpx
import pytest

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import ModelMessage
from fastfence.modules.control.persistence.models import OllamaModels


async def test_user_reported_incomplete_chat_response_fails_closed(monkeypatch):
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"message": {"content": "Hello from upstream"}}
                )
            ),
            **kwargs,
        ),
    )
    with pytest.raises(ModelUnavailableError, match="Model unavailable"):
        await OllamaModels("http://local").complete(
            "allowed-model",
            "",
            12,
            1000,
            messages=[ModelMessage(role="user", content="Hi")],
        )


@pytest.fixture
def provider_reply():
    return {
        "response": "Hello",
        "message": {"role": "assistant", "content": "Hello"},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 3,
        "eval_count": 5,
    }


def install_reply(monkeypatch, reply):
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=reply)
            ),
            **kwargs,
        ),
    )


async def complete(chat):
    return await OllamaModels("http://local").complete(
        "allowed-model",
        "Hi",
        12,
        1000,
        messages=[ModelMessage(role="user", content="Hi")] if chat else None,
    )


@pytest.mark.parametrize("chat", [False, True])
@pytest.mark.parametrize(
    "field", ["done", "done_reason", "prompt_eval_count", "eval_count"]
)
async def test_required_completion_metadata(
    monkeypatch, provider_reply, chat, field
):
    provider_reply.pop(field)
    install_reply(monkeypatch, provider_reply)
    with pytest.raises(ModelUnavailableError):
        await complete(chat)


@pytest.mark.parametrize("chat", [False, True])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("done", False),
        ("done", None),
        ("done", 1),
        ("done", "true"),
        ("done_reason", None),
        ("done_reason", "load"),
        ("done_reason", False),
        ("prompt_eval_count", None),
        ("prompt_eval_count", -1),
        ("prompt_eval_count", True),
        ("prompt_eval_count", "3"),
        ("prompt_eval_count", 3.0),
        ("eval_count", None),
        ("eval_count", -1),
        ("eval_count", True),
        ("eval_count", "5"),
        ("eval_count", 5.0),
        ("eval_count", 13),
        ("error", "provider secret details"),
        ("error", ""),
    ],
)
async def test_invalid_completion_metadata(
    monkeypatch, provider_reply, chat, field, value
):
    provider_reply[field] = value
    install_reply(monkeypatch, provider_reply)
    with pytest.raises(ModelUnavailableError) as error:
        await complete(chat)
    assert str(error.value) == "Model unavailable or invalid response"


@pytest.mark.parametrize("chat", [False, True])
@pytest.mark.parametrize("reason", ["stop", "length"])
async def test_explicit_zero_usage_and_finish_reason_are_preserved(
    monkeypatch, provider_reply, chat, reason
):
    provider_reply.update(prompt_eval_count=0, eval_count=0, done_reason=reason)
    provider_reply.update(model="provider-name", total_duration=0, error=None)
    install_reply(monkeypatch, provider_reply)
    output, usage = await complete(chat)
    assert usage == 0 and output == {
        "text": "Hello",
        "model": "allowed-model",
        "finish_reason": reason,
    }


@pytest.mark.parametrize(
    "message",
    [
        None,
        {},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": 1},
        {"role": "assistant", "content": "Hello", "tool_calls": [{}]},
        {"role": "assistant", "content": "Hello", "images": ["hidden"]},
    ],
)
async def test_invalid_chat_text_envelope(monkeypatch, provider_reply, message):
    provider_reply["message"] = message
    install_reply(monkeypatch, provider_reply)
    with pytest.raises(ModelUnavailableError):
        await complete(True)


@pytest.mark.parametrize("text", [None, 1, {}, []])
async def test_generate_requires_string(monkeypatch, provider_reply, text):
    provider_reply["response"] = text
    install_reply(monkeypatch, provider_reply)
    with pytest.raises(ModelUnavailableError):
        await complete(False)
