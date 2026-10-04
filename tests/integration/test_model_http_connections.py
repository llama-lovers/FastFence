"""Real loopback sockets verify reuse and deadlines while waiting for a pool slot."""

import asyncio
import json

import pytest

from fastfence.modules.control.persistence import model_http
from fastfence.modules.control.persistence.model_http import ModelHTTP
from fastfence.modules.control.persistence.models import OllamaModels


async def test_native_model_reuses_one_tcp_connection_for_distinct_calls():
    connections = []
    payloads = []
    completed = asyncio.Event()

    async def serve(reader, writer):
        connections.append(writer.get_extra_info("peername"))
        try:
            while True:
                header = await reader.readuntil(b"\r\n\r\n")
                length = next(
                    int(line.split(b":", 1)[1])
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
                payload = json.loads(await reader.readexactly(length))
                payloads.append(payload)
                body = json.dumps(
                    {
                        "response": payload["prompt"],
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 1,
                        "eval_count": 1,
                    }
                ).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            completed.set()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    adapter = OllamaModels(
        f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    )
    try:
        async with server:
            for index in range(10):
                output, tokens = await adapter.complete(
                    "fixture", f"hello {index}", 10, 1000
                )
                assert output["text"] == f"hello {index}"
                assert tokens == 2
            await adapter.aclose()
        assert len(connections) == 1
        assert len(payloads) == 10
    finally:
        await adapter.aclose()
        await asyncio.wait_for(completed.wait(), 1)


async def test_total_deadline_includes_wait_for_real_pool_connection(
    monkeypatch,
):
    monkeypatch.setattr(model_http, "MAX_CONNECTIONS", 1)
    entered = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()
    connections = []

    async def serve(reader, writer):
        connections.append(writer.get_extra_info("peername"))
        await reader.readuntil(b"\r\n\r\n")
        entered.set()
        await release.wait()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        completed.set()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    pool = ModelHTTP()
    first = asyncio.create_task(pool.post(url, json={}, timeout_ms=2000))
    try:
        async with server:
            await asyncio.wait_for(entered.wait(), 1)
            with pytest.raises(TimeoutError):
                await pool.post(url, json={}, timeout_ms=30)
            assert not first.done()
            assert pool._pending == 1
            assert len(connections) == 1
            release.set()
            assert (await first).status_code == 200
            assert pool._pending == 0
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)
        await pool.aclose()
        await asyncio.wait_for(completed.wait(), 1)
