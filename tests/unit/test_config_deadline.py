"""Exercise the remote configuration deadline over real loopback HTTP."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field

from fastfence.modules.control.persistence.config_providers import (
    ConfigSourceError,
    HttpConfigProvider,
)
from fastfence.modules.control.persistence.policy import PolicyStore


class LiveSourceState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    body: bytes
    drip: bool = False
    headers_delay: float = 0
    disconnected: threading.Event = Field(default_factory=threading.Event)


@pytest.fixture
def live_source(configuration):
    policy_path, feed_path = configuration
    state = LiveSourceState(
        body=json.dumps(
            {
                "policy": yaml.safe_load(policy_path.read_text()),
                "feed": json.loads(feed_path.read_text()),
            }
        ).encode()
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(state.headers_delay)
            self.send_response(200)
            self.send_header("Content-Length", str(len(state.body)))
            self.end_headers()
            try:
                if not state.drip:
                    self.wfile.write(state.body)
                    return
                for offset in range(0, len(state.body), 20):
                    self.wfile.write(state.body[offset : offset + 20])
                    self.wfile.flush()
                    time.sleep(0.03)
            except (BrokenPipeError, ConnectionResetError):
                state.disconnected.set()

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/bundle", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_slow_drip_stops_at_total_deadline_and_disconnects(live_source):
    url, state = live_source
    provider = HttpConfigProvider(url, timeout=0.1, max_bytes=8192)
    state.drip = True
    started = time.monotonic()
    with pytest.raises(ConfigSourceError, match="^source_timeout$"):
        provider.read()
    assert time.monotonic() - started < 0.4
    assert state.disconnected.wait(timeout=0.3)


def test_slow_headers_have_the_same_total_deadline(live_source):
    url, state = live_source
    state.headers_delay = 0.4
    provider = HttpConfigProvider(url, timeout=0.1, max_bytes=8192)
    started = time.monotonic()
    with pytest.raises(ConfigSourceError, match="^source_timeout$"):
        provider.read()
    assert time.monotonic() - started < 0.3


async def test_slow_drip_refresh_retains_last_good_bundle(
    configuration, live_source
):
    url, state = live_source
    store = PolicyStore(*configuration, config_url=url, fetch_timeout=0.1)
    previous = store.snapshot()
    state.drip = True
    started = time.monotonic()
    assert not await store.refresh()
    assert time.monotonic() - started < 0.4
    assert store.snapshot() is previous
    assert store.diagnostics()["last_error"] == "source_timeout"
    assert state.disconnected.wait(timeout=0.3)


async def test_http_startup_inside_an_existing_loop_joins_worker(
    configuration, live_source
):
    url, state = live_source
    store = PolicyStore(*configuration, config_url=url, fetch_timeout=0.5)
    assert store.snapshot().policy.version == 1
    assert await store.refresh() is False
    assert not any(
        thread.name.startswith("fastfence-config-fetch")
        for thread in threading.enumerate()
    )
    state.drip = True
    provider = HttpConfigProvider(url, timeout=0.1, max_bytes=8192)
    started = time.monotonic()
    with pytest.raises(ConfigSourceError, match="^source_timeout$"):
        provider.read()
    assert time.monotonic() - started < 0.4
    assert not any(
        thread.name.startswith("fastfence-config-fetch")
        for thread in threading.enumerate()
    )


async def test_deadline_closes_an_async_response_stream(monkeypatch):
    state = {"closed": False, "cancelled": False}

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                while True:
                    yield b"{}"
                    await asyncio.sleep(0.03)
            except asyncio.CancelledError:
                state["cancelled"] = True
                raise

        async def aclose(self):
            state["closed"] = True

    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=SlowStream())
    )
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=transport, **kwargs),
    )
    provider = HttpConfigProvider("http://127.0.0.1/config", 0.1, 8192)
    with pytest.raises(ConfigSourceError, match="^source_timeout$"):
        provider.read()
    assert state == {"closed": True, "cancelled": True}
