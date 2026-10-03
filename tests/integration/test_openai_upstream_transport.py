"""Real loopback HTTP exchange with synthetic provider output; no inference."""

import asyncio
import json

import pytest

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.persistence.openai_models import OpenAIModels


@pytest.mark.parametrize("finish_reason", ["stop", "length"])
async def test_actual_http_prompt_mapping_and_usage(finish_reason):
    requests = []

    async def serve(reader, writer):
        header = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":", 1)[1])
            for line in header.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        requests.append((header, json.loads(await reader.readexactly(length))))
        body = json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "Synthetic output",
                        },
                        "finish_reason": finish_reason,
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 3,
                    "total_tokens": 8,
                },
            }
        ).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
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
        output, tokens = await OpenAIModels(
            f"http://127.0.0.1:{port}/v1"
        ).complete("fixture", "Hello", 10, 1000)
    assert tokens == 8 and output["text"] == "Synthetic output"
    assert output["finish_reason"] == finish_reason
    assert requests[0][0].startswith(b"POST /v1/chat/completions HTTP/1.1")
    assert requests[0][1]["messages"] == [{"role": "user", "content": "Hello"}]


async def test_total_deadline_cancels_slow_transport(monkeypatch):
    import httpx

    async def slow(_):
        await asyncio.sleep(5)
        raise AssertionError("deadline must cancel transport")

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(slow), **kwargs
        ),
    )
    with pytest.raises(ModelUnavailableError):
        await OpenAIModels("http://127.0.0.1:1234/v1").complete(
            "fixture", "Hello", 10, 50
        )
