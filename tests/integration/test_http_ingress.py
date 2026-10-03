"""Protected REST input is authenticated and bounded before JSON parsing."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from fastfence.app.factory import create_app
from fastfence.app.interfaces.http.ingress import (
    INVOCATION_BODY_BYTES,
    ProtectedRestIngress,
)
from fastfence.shared.settings.app_settings import AppSettings
from tests.fixtures.auth import headers


async def raw_request(app, path, chunks, *, token=None, extra_headers=()):
    received = 0
    sent = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json"), *extra_headers],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
    }
    if token:
        scope["headers"].append((b"authorization", f"Bearer {token}".encode()))

    async def receive():
        nonlocal received
        if received < len(chunks):
            chunk = chunks[received]
            received += 1
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": received < len(chunks),
            }
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    body = b"".join(message.get("body", b"") for message in sent)
    return start, body, received


@pytest.mark.parametrize(
    "path",
    [
        "/api/invoke",
        "/api/models/complete",
        "/api/admin/rules/preview",
        "/api/admin/policies/draft",
        "/api/admin/policies/activate",
    ],
)
def test_unauthenticated_rest_never_consumes_or_parses_body(
    app, monkeypatch, path
):
    async def forbidden_json(request):
        raise AssertionError("Unauthenticated body reached JSON parser")

    monkeypatch.setattr(Request, "json", forbidden_json)
    start, body, received = asyncio.run(
        raw_request(app, path, [b"{" * (INVOCATION_BODY_BYTES + 1)])
    )
    assert start["status"] == 401
    assert received == 0
    assert json.loads(body) == {"detail": "Verified bearer credential required"}
    response_headers = dict(start["headers"])
    assert response_headers[b"cache-control"] == b"no-store"
    assert response_headers[b"x-content-type-options"] == b"nosniff"


def test_execution_identity_cannot_submit_management_body(
    app, tokens, monkeypatch
):
    async def forbidden_json(request):
        raise AssertionError("Unauthorized management body reached parser")

    monkeypatch.setattr(Request, "json", forbidden_json)
    start, body, received = asyncio.run(
        raw_request(
            app,
            "/api/admin/rules/preview",
            [b"not-json"],
            token=tokens["analyst-blue"],
            extra_headers=[(b"x-role", b"admin")],
        )
    )
    assert start["status"] == 403
    assert json.loads(body) == {"detail": "Management credential required"}
    assert received == 0


@pytest.mark.parametrize("content_length", [None, b"1", b"9000000"])
def test_streamed_byte_limit_does_not_trust_content_length(
    app, tokens, monkeypatch, content_length
):
    async def forbidden_json(request):
        raise AssertionError("Oversized body reached JSON parser")

    monkeypatch.setattr(Request, "json", forbidden_json)
    extra = (
        [] if content_length is None else [(b"content-length", content_length)]
    )
    start, body, received = asyncio.run(
        raw_request(
            app,
            "/api/invoke",
            [b"x" * INVOCATION_BODY_BYTES, b"x", b"unread remainder"],
            token=tokens["analyst-blue"],
            extra_headers=extra,
        )
    )
    assert start["status"] == 413
    assert received == 2
    assert json.loads(body) == {"detail": "Request body too large"}
    assert app.state.engine.ledger.stats()["requests"] == 0


def test_exact_wire_limit_preserves_ordinary_controlled_call(
    client, app, tokens, monkeypatch
):
    calls = []

    async def call(tool, arguments, identity):
        calls.append((identity.subject, tool, arguments))
        return {"answer": "Safe result"}

    monkeypatch.setattr(app.state.engine.tools, "call", call)
    body = json.dumps(
        {"tool": "knowledge.search", "arguments": {"query": "forecast"}}
    )
    body += " " * (INVOCATION_BODY_BYTES - len(body))
    response = client.post(
        "/api/invoke",
        content=body,
        headers={**headers(tokens), "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "allowed"
    assert calls == [
        ("analyst-blue", "knowledge.search", {"query": "forecast"})
    ]
    assert app.state.engine.ledger.stats()["requests"] == 1


def test_escaped_supported_model_payload_remains_usable(
    client, app, tokens, monkeypatch
):
    policy = app.state.runtime.snapshot().policy.editable()
    policy["version"] += 1
    policy["max_input_bytes"] = 65536
    assert (
        client.put(
            "/api/admin/policy",
            json=policy,
            headers=headers(tokens, "security-admin"),
        ).status_code
        == 200
    )
    prompt = "\u0081" * 20000
    seen = []

    async def complete(model, value, maximum, timeout):
        seen.append(value)
        return {"text": "Safe result", "finish_reason": "stop"}, 4

    monkeypatch.setattr(app.state.engine.models, "complete", complete)
    body = json.dumps({"model": "qwen3:0.6b", "prompt": prompt})
    assert 65536 < len(body) < INVOCATION_BODY_BYTES
    response = client.post(
        "/api/models/complete",
        content=body,
        headers={**headers(tokens), "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "allowed"
    assert seen == [prompt]


def test_management_oversize_and_malformed_json_do_not_change_policy(
    client, app, tokens
):
    original = app.state.runtime.snapshot()
    admin = headers(tokens, "security-admin")
    response = client.put(
        "/api/admin/policy",
        content=b"x" * (INVOCATION_BODY_BYTES + 1),
        headers=admin,
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
    malformed = client.put("/api/admin/policy", content="{", headers=admin)
    assert malformed.status_code == 422
    assert malformed.json() == {"detail": "Invalid request schema"}
    assert app.state.runtime.snapshot() is original


def test_unauthenticated_deep_json_is_rejected_before_parser(client, app):
    body = '{"arguments":{"query":' + "[" * 10000 + "0" + "]" * 10000 + "}}"
    assert client.post("/api/invoke", content=body).status_code == 401
    assert app.state.engine.ledger.stats()["requests"] == 0
    assert client.get("/health").status_code == 200


def test_disconnected_body_never_reaches_downstream(app, tokens):
    async def run():
        messages = iter(
            [
                {"type": "http.request", "body": b"{", "more_body": True},
                {"type": "http.disconnect"},
            ]
        )

        async def receive():
            return next(messages)

        async def forbidden(*args):
            raise AssertionError(
                "Disconnected stream reached application or response"
            )

        ingress = ProtectedRestIngress(
            forbidden, app.state.runtime, INVOCATION_BODY_BYTES
        )
        await ingress(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/invoke",
                "headers": [
                    (
                        b"authorization",
                        f"Bearer {tokens['analyst-blue']}".encode(),
                    )
                ],
            },
            receive,
            forbidden,
        )

    asyncio.run(run())
    assert app.state.engine.ledger.stats()["requests"] == 0


def test_management_envelope_uses_trusted_configured_limit(project, tokens):
    instance = create_app(
        AppSettings(
            root=project,
            state=project / "state",
            max_config_source_bytes=1024 * 1024,
            ollama_url="http://127.0.0.1:1",
            kev_url="http://127.0.0.1:1",
        )
    )
    with TestClient(instance) as client:
        policy = instance.state.runtime.snapshot().policy.editable()
        policy["version"] += 1
        body = json.dumps(policy)
        body += " " * (INVOCATION_BODY_BYTES + 1 - len(body))
        response = client.put(
            "/api/admin/policy",
            content=body,
            headers={
                **headers(tokens, "security-admin"),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200
        assert (
            instance.state.runtime.snapshot().policy.version
            == policy["version"]
        )
        assert (
            client.post(
                "/api/invoke", content=body, headers=headers(tokens)
            ).status_code
            == 413
        )
