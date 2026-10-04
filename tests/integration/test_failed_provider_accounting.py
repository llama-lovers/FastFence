"""Real provider HTTP failures retain reservations instead of bypassing budgets."""

import asyncio
import json

import pytest

from fastfence.modules.control.domain.models import ModelCall
from fastfence.modules.control.persistence.models import OllamaModels
from fastfence.modules.control.persistence.openai_models import OpenAIModels
from tests.fixtures.policy import configure_policy


@pytest.mark.parametrize(
    "mode",
    [
        "excess_usage",
        "missing_usage",
        "http_error",
        "native_incomplete",
        "native_missing_usage",
        "native_not_done",
    ],
)
async def test_unknown_provider_usage_charges_reservation_and_blocks_retry(
    app, tokens, mode
):
    engine = app.state.engine
    configure_policy(
        engine, lambda data: data["budgets"]["analyst"].update(tokens=1150)
    )
    attempts = []

    async def serve(reader, writer):
        header = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":", 1)[1])
            for line in header.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        attempts.append(json.loads(await reader.readexactly(length)))
        reply = {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 70,
                "total_tokens": 82,
            },
        }
        if mode == "missing_usage":
            reply.pop("usage")
        if mode.startswith("native_"):
            reply = {"response": "Hello"}
            if mode == "native_missing_usage":
                reply.update(done=True, done_reason="stop")
            if mode == "native_not_done":
                reply.update(
                    done=False,
                    done_reason="stop",
                    prompt_eval_count=5,
                    eval_count=3,
                )
        body = json.dumps(reply).encode()
        status = (
            b"500 Internal Server Error" if mode == "http_error" else b"200 OK"
        )
        writer.write(
            b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\n"
            b"Content-Length: "
            + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    async with server:
        port = server.sockets[0].getsockname()[1]
        engine.models = (
            OllamaModels(f"http://127.0.0.1:{port}")
            if mode.startswith("native_")
            else OpenAIModels(f"http://127.0.0.1:{port}/v1")
        )
        identity = app.state.identities.authenticate(tokens["analyst-blue"])
        call = ModelCall(model="qwen3:0.6b", prompt="Hi", max_output_tokens=64)
        failed = await engine.invoke(identity, call)
        denied = await engine.invoke(identity, call)

    assert failed.reason == "model_unavailable_fail_closed"
    assert failed.upstream_executed and failed.output is None
    assert failed.tokens == 1103
    assert denied.reason == "budget_tokens" and not denied.upstream_executed
    assert denied.tokens == 0 and len(attempts) == 1
    row = engine.ledger.budgets()[0]
    assert row["tokens"] == 1103 and row["inflight"] == 0
    if mode.startswith("native_"):
        assert attempts[0]["options"]["num_predict"] == 64
    else:
        assert attempts[0]["max_tokens"] == 64
