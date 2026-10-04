"""Actual mounted protocols cancel queued engine work on ASGI disconnect."""

import asyncio
import json

import pytest

from fastfence.app.factory import create_app
from fastfence.modules.control.application.services.admission import (
    RequestAdmission,
)
from fastfence.shared.request_size import request_size
from fastfence.shared.settings.app_settings import AppSettings
from tests.fixtures.policy import configure_policy


def invocation(path):
    if path == "/api/documents/markdown":
        return b"synthetic-document", b"image/png", b"model=qwen3%3A0.6b"
    if path == "/acp/runs":
        data = {
            "agent_name": "peer",
            "input": [{"role": "user", "parts": [{"content": "hello"}]}],
        }
    elif path == "/v1/chat/completions":
        data = {
            "model": "qwen3:0.6b",
            "messages": [{"role": "user", "content": "hello"}],
        }
    elif path == "/api/models/complete":
        data = {"model": "qwen3:0.6b", "prompt": "hello"}
    elif path == "/mcp/":
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "invoke",
                "arguments": {
                    "tool": "acp.peer",
                    "arguments": {"input": [{"role": 0, "parts": ["hello"]}]},
                },
            },
        }
    else:
        data = {
            "tool": "acp.peer",
            "arguments": {"input": [{"role": 0, "parts": ["hello"]}]},
        }
    return json.dumps(data).encode(), b"application/json", b""


@pytest.mark.parametrize(
    "path",
    [
        "/api/invoke",
        "/api/models/complete",
        "/v1/chat/completions",
        "/acp/runs",
        "/mcp/",
        "/api/documents/markdown",
    ],
)
async def test_disconnect_removes_actual_protocol_queue_entry(
    project, tokens, monkeypatch, path
):
    app = create_app(
        AppSettings(
            root=project,
            state=project / "state",
            acp_agents={
                "peer": {"base_url": "http://127.0.0.1:1", "agent_name": "peer"}
            },
        )
    )
    engine = app.state.engine
    admission = RequestAdmission(concurrency=1, max_waiting=2)
    engine.admission = admission

    def policy(data):
        data["tools"]["acp.peer"] = {
            "roles": ["analyst"],
            "timeout_ms": 1000,
            "cost_microusd": 100,
        }

    configure_policy(engine, policy)
    executed = []
    retained_bytes = []
    original_invoke = engine.invoke

    async def measured_invoke(identity, call, **options):
        retained_bytes.append(options.get("preparation_bytes", 0))
        return await original_invoke(identity, call, **options)

    monkeypatch.setattr(engine, "invoke", measured_invoke)

    async def forbidden(*args, **kwargs):
        executed.append(True)
        raise AssertionError("Queued request reached upstream")

    monkeypatch.setattr(engine.tools, "call", forbidden)
    monkeypatch.setattr(engine.models, "complete", forbidden)
    monkeypatch.setattr(engine.scanner, "assess", forbidden)
    body, media, query = invocation(path)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query,
        "headers": [
            (b"host", b"localhost"),
            (b"authorization", ("Bearer " + tokens["analyst-blue"]).encode()),
            (b"content-type", media),
            (b"accept", b"application/json, text/event-stream"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 80),
    }
    messages = asyncio.Queue()
    messages.put_nowait(
        {"type": "http.request", "body": body, "more_body": False}
    )
    responses = []

    async def send(message):
        responses.append(message)

    async with app.router.lifespan_context(app):
        await admission.acquire(0, ("fixture", "holding"), 1)
        task = asyncio.create_task(app(scope, messages.get, send))
        try:
            async with asyncio.timeout(3):
                while admission.snapshot()["waiting"] != 1:
                    if task.done():
                        await task
                        pytest.fail(f"Request never queued: {responses}")
                    await asyncio.sleep(0.005)
            assert request_size(scope) == len(body)
            assert retained_bytes == [len(body)]
            assert engine.ledger.budgets() == []
            messages.put_nowait({"type": "http.disconnect"})
            await asyncio.wait_for(task, 3)
            async with asyncio.timeout(3):
                while admission.snapshot()["waiting"]:
                    await asyncio.sleep(0.005)
            assert admission.snapshot()["waiting_bytes"] == 0
            assert engine.ledger.budgets() == []
            assert not executed
            assert any(
                row["reason"] == "request_cancelled"
                for row in engine.ledger.audit()
            )
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            admission.release(("fixture", "holding"))
        assert not await admission.acquire(0, ("fixture", "next"), 1)
        admission.release(("fixture", "next"))
