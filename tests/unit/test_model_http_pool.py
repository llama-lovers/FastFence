"""Pooled transport preserves bounded, isolated model request lifetimes."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.persistence import model_http
from fastfence.modules.control.persistence.model_http import ModelHTTP
from fastfence.modules.control.persistence.models import (
    OllamaModels,
    SemanticScanner,
)
from fastfence.modules.control.persistence.openai_models import OpenAIModels


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    clients = []
    options = []

    def create(**kwargs):
        options.append(kwargs)
        client = original(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", create)
    return clients, options


async def test_lazy_reuse_without_cookie_or_header_cross_request_state(
    monkeypatch,
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, headers={"Set-Cookie": "user=first; Path=/"}, json={}
        )

    clients, options = install_transport(monkeypatch, handler)
    pool = ModelHTTP()
    assert clients == []
    await pool.post(
        "https://model.test/",
        json={"user": 1},
        timeout_ms=1000,
        headers={"Authorization": "Bearer synthetic-first"},
    )
    await pool.post("https://model.test/", json={"user": 2}, timeout_ms=1000)
    assert len(clients) == 1
    assert len(clients[0].cookies) == 0
    assert "cookie" not in requests[1].headers
    assert "authorization" not in requests[1].headers
    assert requests[0].content != requests[1].content
    assert options[0]["trust_env"] is options[0]["follow_redirects"] is False
    assert options[0]["limits"].max_connections == 32
    assert options[0]["limits"].max_keepalive_connections == 32
    await pool.aclose()
    await pool.aclose()
    assert clients[0].is_closed
    with pytest.raises(RuntimeError, match="unavailable"):
        await pool.post("https://model.test/", json={}, timeout_ms=1000)
    assert len(clients) == 1


async def test_adapters_stay_lazy_until_async_use(monkeypatch):
    clients, _ = install_transport(monkeypatch, lambda _: httpx.Response(200))
    adapters = [
        OllamaModels("http://localhost:11434"),
        OpenAIModels("http://localhost:11434/v1"),
        SemanticScanner("http://localhost:11434", "http://localhost:9000"),
    ]
    assert clients == []
    for adapter in adapters:
        await adapter.aclose()
    assert clients == []


@pytest.mark.parametrize("scanner_fails", [False, True])
async def test_runtime_shutdown_closes_models_even_if_scanner_fails(
    scanner_fails,
):
    scanner = SimpleNamespace(
        aclose=AsyncMock(
            side_effect=ValueError("closed") if scanner_fails else None
        )
    )
    models = SimpleNamespace(aclose=AsyncMock())
    ledger = SimpleNamespace(close=Mock())
    aliases = SimpleNamespace(close=Mock())
    engine = SimpleNamespace(
        scanner=scanner, models=models, anonymization=aliases
    )
    runtime = ControlRuntime(None, None, ledger, engine)
    if scanner_fails:
        with pytest.raises(ValueError, match="closed"):
            await runtime.aclose()
    else:
        await runtime.aclose()
    scanner.aclose.assert_awaited_once()
    models.aclose.assert_awaited_once()
    ledger.close.assert_called_once()
    aliases.close.assert_called_once()


async def test_bounded_pending_admission_and_cancellation_release(monkeypatch):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def handler(_):
        nonlocal calls
        calls += 1
        if calls == model_http.MAX_PENDING_REQUESTS:
            entered.set()
        await release.wait()
        return httpx.Response(200, json={})

    install_transport(monkeypatch, handler)
    pool = ModelHTTP()
    pending = [
        asyncio.create_task(
            pool.post("https://model.test/", json={}, timeout_ms=10000)
        )
        for _ in range(model_http.MAX_PENDING_REQUESTS)
    ]
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        with pytest.raises(RuntimeError, match="unavailable"):
            await pool.post("https://model.test/", json={}, timeout_ms=1000)
        assert calls == 128
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        assert pool._pending == 0
        release.set()
        assert (
            await pool.post("https://model.test/", json={}, timeout_ms=1000)
        ).status_code == 200
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        await pool.aclose()


class SlowStream(httpx.AsyncByteStream):
    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        yield b"start"
        await asyncio.sleep(10)
        yield b"end"

    async def aclose(self):
        self.closed = True


async def test_total_stream_deadline_closes_response_and_releases_capacity(
    monkeypatch,
):
    stream = SlowStream()
    install_transport(monkeypatch, lambda _: httpx.Response(200, stream=stream))
    pool = ModelHTTP()
    try:
        with pytest.raises(TimeoutError):
            await pool.post("https://model.test/", json={}, timeout_ms=20)
        assert stream.closed
        assert pool._pending == 0
    finally:
        await pool.aclose()


@pytest.mark.parametrize("mode", ["oversize", "encoded", "redirect"])
async def test_response_bounds_and_no_redirects(monkeypatch, mode):
    requests = []

    def handler(request):
        requests.append(request)
        if mode == "oversize":
            return httpx.Response(200, content=b"x" * 33)
        if mode == "encoded":
            return httpx.Response(
                200,
                headers={"Content-Encoding": "br"},
                stream=httpx.ByteStream(b"x"),
            )
        return httpx.Response(302, headers={"Location": "https://other.test/"})

    install_transport(monkeypatch, handler)
    pool = ModelHTTP()
    try:
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            await pool.post(
                "https://model.test/",
                json={},
                timeout_ms=1000,
                max_response_bytes=32,
            )
        assert len(requests) == 1
        assert pool._pending == 0
    finally:
        await pool.aclose()
