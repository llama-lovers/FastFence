"""ACP reuses bounded transport without sharing caller state or leaking slots."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import SecretStr

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.domain.exceptions import (
    ToolCapacityExceededError,
)
from fastfence.modules.control.domain.models import Identity
from fastfence.modules.control.persistence.acp_tools import ACPTools
from fastfence.modules.control.persistence.model_http import (
    MAX_PENDING_REQUESTS,
)
from fastfence.shared.acp import ACPAgentSettings

IDENTITY = Identity(subject="caller", tenant="blue", roles=["analyst"])
INPUT = {"input": [{"role": 0, "parts": ["hello"]}]}


def adapter():
    return ACPTools(
        {
            "first": ACPAgentSettings(
                base_url="https://first.test",
                agent_name="remote",
                api_key=SecretStr("synthetic-first"),
            ),
            "second": ACPAgentSettings(
                base_url="https://second.test", agent_name="remote"
            ),
        }
    )


def response():
    return {
        "agent_name": "remote",
        "status": "completed",
        "output": [{"role": "agent", "parts": [{"content": "hello"}]}],
    }


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    clients = []

    def factory(**options):
        client = original(transport=httpx.MockTransport(handler), **options)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return clients


async def test_one_lazy_client_and_no_alias_credential_or_cookie_leak(
    monkeypatch,
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"Set-Cookie": "private=first; Path=/"},
            json=response(),
        )

    clients = transport(monkeypatch, handler)
    tools = adapter()
    assert clients == []
    try:
        for alias in ("first", "second", "first"):
            assert await tools.call("acp." + alias, INPUT, IDENTITY)
        assert len(clients) == 1
        assert requests[0].headers["authorization"] == "Bearer synthetic-first"
        assert "authorization" not in requests[1].headers
        assert all("cookie" not in request.headers for request in requests)
        assert not clients[0].cookies
    finally:
        await tools.aclose()
    assert clients[0].is_closed
    await tools.aclose()
    with pytest.raises(RuntimeError, match="ACP agent unavailable"):
        await tools.call("acp.first", INPUT, IDENTITY)
    assert len(clients) == 1


async def test_aggregate_alias_admission_and_cancelled_slots_recover(
    monkeypatch,
):
    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def handler(_):
        nonlocal count
        count += 1
        if count == MAX_PENDING_REQUESTS:
            entered.set()
        await release.wait()
        return httpx.Response(200, json=response())

    transport(monkeypatch, handler)
    tools = adapter()
    tasks = [
        asyncio.create_task(
            tools.call(
                "acp.first" if index % 2 else "acp.second", INPUT, IDENTITY
            )
        )
        for index in range(MAX_PENDING_REQUESTS)
    ]
    try:
        await asyncio.wait_for(entered.wait(), 2)
        with pytest.raises(ToolCapacityExceededError):
            await tools.call("acp.second", INPUT, IDENTITY)
        assert count == MAX_PENDING_REQUESTS
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert tools._http._pending == 0
        release.set()
        assert await tools.call("acp.first", INPUT, IDENTITY)
        assert tools._http._pending == 0
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await tools.aclose()


@pytest.mark.parametrize("failure", [None, "scanner", "models", "tools"])
async def test_runtime_closes_every_provider_even_if_another_close_fails(
    failure,
):
    providers = {
        name: SimpleNamespace(
            aclose=AsyncMock(
                side_effect=RuntimeError("fixture") if name == failure else None
            )
        )
        for name in ("scanner", "models", "tools")
    }
    ledger, anonymization = (
        SimpleNamespace(close=Mock()),
        SimpleNamespace(close=Mock()),
    )
    runtime = ControlRuntime(
        None,
        None,
        ledger,
        SimpleNamespace(**providers, anonymization=anonymization),
    )
    if failure:
        with pytest.raises(RuntimeError, match="fixture"):
            await runtime.aclose()
    else:
        await runtime.aclose()
    for provider in providers.values():
        provider.aclose.assert_awaited_once()
    ledger.close.assert_called_once()
    anonymization.close.assert_called_once()


async def test_real_acp_pool_reuses_connection_and_bounds_wait_deadline(
    monkeypatch,
):
    import json

    from fastfence.modules.control.persistence import model_http

    monkeypatch.setattr(model_http, "MAX_CONNECTIONS", 1)
    entered, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    connections, requests = [], []

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
                requests.append(json.loads(await reader.readexactly(length)))
                entered.set()
                await release.wait()
                body = json.dumps(response()).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Length: "
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
            closed.set()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    tools = ACPTools(
        {
            "long": ACPAgentSettings(
                base_url=url, agent_name="remote", timeout_seconds=2
            ),
            "short": ACPAgentSettings(
                base_url=url, agent_name="remote", timeout_seconds=0.1
            ),
        }
    )
    first = asyncio.create_task(tools.call("acp.long", INPUT, IDENTITY))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(TimeoutError, match="ACP agent timeout"):
            await tools.call("acp.short", INPUT, IDENTITY)
        assert tools._http._pending == 1
        assert len(connections) == len(requests) == 1
        release.set()
        assert await asyncio.wait_for(first, 3)
        assert await asyncio.wait_for(
            tools.call("acp.long", INPUT, IDENTITY), 3
        )
        assert len(connections) == 1 and len(requests) == 2
        assert tools._http._pending == 0
        await tools.aclose()
    finally:
        release.set()
        first.cancel()
        await asyncio.wait_for(asyncio.gather(first, return_exceptions=True), 1)
        await asyncio.wait_for(tools.aclose(), 1)
        server.close()
        await asyncio.wait_for(server.wait_closed(), 1)
        await asyncio.wait_for(closed.wait(), 1)
