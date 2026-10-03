"""Bounded trusted ACP transport and protocol-only normalization checks."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from fastfence.modules.control.application.facade import build_runtime
from fastfence.modules.control.domain.models import Identity
from fastfence.modules.control.persistence.acp_tools import (
    MAX_RESPONSE_BYTES,
    ACPTools,
)
from fastfence.modules.control.persistence.tools import UnconfiguredTools
from fastfence.shared.acp import (
    ACPAgentSettings,
    ACPInput,
    ACPToolInput,
    project_messages,
    restore_messages,
)
from fastfence.shared.settings.app_settings import AppSettings

IDENTITY = Identity(subject="caller", tenant="blue", roles=["analyst"])
INPUT = {"input": [{"role": 0, "parts": ["hello"]}]}


def response():
    return {
        "agent_name": "remote",
        "status": "completed",
        "output": [{"role": "agent/remote", "parts": [{"content": "hello"}]}],
    }


def provider(url="http://127.0.0.1:9999", **kwargs):
    return ACPTools(
        {"peer": ACPAgentSettings(base_url=url, agent_name="remote", **kwargs)}
    )


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    options = []

    def client(**kwargs):
        options.append(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return options


async def test_sync_wire_call_has_only_trusted_destination_and_server_key(
    monkeypatch,
):
    requests = []
    body = response()
    body["output"][0]["parts"][0]["metadata"] = {"private": "unchecked"}
    body["output"][0]["parts"][0]["name"] = "unchecked-name"
    body["output"][0]["created_at"] = "unchecked-date"
    body["debug"] = "unchecked-debug"

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    options = transport(monkeypatch, handler)
    key = "synthetic-server-only"  # pragma: allowlist secret
    result = await provider(api_key=SecretStr(key)).call(
        "acp.peer", INPUT, IDENTITY
    )
    assert result == {"output": [{"role": 1, "parts": ["hello"]}]}
    request = requests[0]
    assert str(request.url) == "http://127.0.0.1:9999/runs"
    assert request.headers["authorization"] == "Bearer " + key
    sent = json.loads(request.content)
    assert sent == {
        "agent_name": "remote",
        "mode": "sync",
        "input": [
            {
                "role": "user",
                "parts": [
                    {
                        "content": "hello",
                        "content_type": "text/plain",
                        "content_encoding": "plain",
                    }
                ],
            }
        ],
    }
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False
    assert "caller" not in request.content.decode()
    assert "unchecked" not in json.dumps(result)


@pytest.mark.parametrize("status", [201, 202, 302, 401, 500])
async def test_http_failures_never_return_raw_remote_errors(
    monkeypatch, status
):
    transport(
        monkeypatch,
        lambda _: httpx.Response(status, text="PRIVATE upstream failure"),
    )
    with pytest.raises(RuntimeError) as caught:
        await provider().call("acp.peer", INPUT, IDENTITY)
    assert str(caught.value) == "ACP agent unavailable or invalid response"


@pytest.mark.parametrize(
    "change",
    [
        lambda body: body.update(status="created"),
        lambda body: body.update(status="awaiting"),
        lambda body: body.update(status="failed"),
        lambda body: body.update(agent_name="other"),
        lambda body: body.update(session_id="a-session"),
        lambda body: body.update(session={}),
        lambda body: body.update(await_request={}),
        lambda body: body.update(error={}),
        lambda body: body.update(output=[]),
        lambda body: body["output"][0].update(role="system"),
        lambda body: body["output"][0]["parts"][0].update(
            content_url="https://example.org/private"
        ),
        lambda body: body["output"][0]["parts"][0].update(
            content_encoding="base64"
        ),
        lambda body: body["output"][0]["parts"][0].update(
            content_type="image/png"
        ),
        lambda body: body["output"][0]["parts"][0].update(content=123),
        lambda body: body["output"][0]["parts"][0].update(content=""),
        lambda body: body["output"][0]["parts"][0].update(content="x" * 16385),
        lambda body: body.update(output=body["output"] * 33),
    ],
)
async def test_unsupported_or_malformed_runs_fail_closed(monkeypatch, change):
    body = response()
    change(body)
    transport(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(RuntimeError, match="ACP agent unavailable"):
        await provider().call("acp.peer", INPUT, IDENTITY)


@pytest.mark.parametrize(
    "body",
    [
        b'{"status":"completed","status":"failed"}',
        b"not-json",
        b" " * (MAX_RESPONSE_BYTES + 1),
    ],
)
async def test_duplicate_invalid_and_oversize_json_is_rejected(
    monkeypatch, body
):
    transport(monkeypatch, lambda _: httpx.Response(200, content=body))
    with pytest.raises(RuntimeError, match="ACP agent unavailable"):
        await provider().call("acp.peer", INPUT, IDENTITY)


async def test_deadline_and_cancellation_propagate(monkeypatch):
    async def delayed(_):
        await asyncio.sleep(20)
        return httpx.Response(200, json=response())

    transport(monkeypatch, delayed)
    with pytest.raises(TimeoutError, match="ACP agent timeout"):
        await provider(timeout_seconds=0.1).call("acp.peer", INPUT, IDENTITY)
    task = asyncio.create_task(provider().call("acp.peer", INPUT, IDENTITY))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example",
        "https://u:p@example.org",
        "https://example.org?q=x",
        "https://example.org#x",
        "file:///tmp/a",
        "http://127.0.0.1:0",
    ],
)
def test_upstream_urls_are_trusted_https_or_loopback_only(url):
    with pytest.raises(ValueError):
        provider(url)


def test_settings_registry_is_bounded_and_credentials_are_not_represented(
    monkeypatch,
):
    monkeypatch.setenv(
        "FASTFENCE_ACP_AGENTS",
        json.dumps(
            {
                "peer": {
                    "base_url": "https://example.org",
                    "agent_name": "remote",
                    "api_key": "synthetic-private-value",  # pragma: allowlist secret
                }
            }
        ),
    )
    settings = AppSettings()
    assert settings.acp_agents["peer"].agent_name == "remote"
    assert "synthetic-private-value" not in repr(settings)
    with pytest.raises(ValidationError):
        AppSettings(
            acp_agents={
                f"peer-{i}": settings.acp_agents["peer"] for i in range(33)
            }
        )
    with pytest.raises(ValidationError):
        AppSettings(acp_agents={"../bad": settings.acp_agents["peer"]})


def test_sdk_timestamps_nulls_and_agent_roles_are_projected_to_content_only():
    source = {
        "input": [
            {
                "role": "agent/remote",
                "created_at": "2026-10-03T21:28:20.025161Z",
                "completed_at": None,
                "parts": [
                    {
                        "content": "hello",
                        "content_url": None,
                        "metadata": None,
                        "name": None,
                    }
                ],
            }
        ]
    }
    message = ACPInput.model_validate(source)
    projected = project_messages(message.input)
    assert projected == [{"role": 1, "parts": ["hello"]}]
    assert restore_messages(projected)[0]["role"] == "agent"
    assert "created_at" not in message.model_dump(exclude_none=True)["input"][0]
    source["input"][0]["parts"][0]["metadata"] = {"instruction": "uninspected"}
    with pytest.raises(ValueError):
        ACPInput.model_validate(source)


@pytest.mark.parametrize("role", [True, False, "0", 2, -1])
def test_internal_roles_are_strict_codes(role):
    payload = deepcopy(INPUT)
    payload["input"][0]["role"] = role
    with pytest.raises(ValueError):
        ACPToolInput.model_validate(payload)


def test_runtime_wires_acp_and_rejects_ambiguous_tool_provider(project):
    settings = AppSettings(
        root=project,
        acp_agents={
            "peer": ACPAgentSettings(
                base_url="https://example.org", agent_name="remote"
            )
        },
    )
    runtime = build_runtime(settings)
    try:
        assert runtime.engine.tools.supports("acp.peer")
        assert not runtime.engine.tools.supports("acp.unknown")
    finally:
        runtime.close()
    with pytest.raises(ValueError, match="Choose ACP agents"):
        build_runtime(settings, tools=UnconfiguredTools())


async def test_actual_loopback_http_exchange_has_sync_completed_text():
    requests = []

    async def serve(reader, writer):
        header = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":", 1)[1])
            for line in header.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        requests.append(json.loads(await reader.readexactly(length)))
        body = json.dumps(response()).encode()
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
        result = await provider(f"http://127.0.0.1:{port}").call(
            "acp.peer", INPUT, IDENTITY
        )
    assert result == {"output": [{"role": 1, "parts": ["hello"]}]}
    assert len(requests) == 1 and requests[0]["mode"] == "sync"


def test_utf8_aggregate_bound_applies_to_wire_and_internal_messages():
    text = "ą" * 10_000
    with pytest.raises(ValueError, match="byte limit"):
        ACPInput.model_validate(
            {"input": [{"role": "user", "parts": [{"content": text}] * 4}]}
        )
    with pytest.raises(ValueError, match="byte limit"):
        ACPToolInput.model_validate(
            {"input": [{"role": 0, "parts": [text] * 4}]}
        )


async def test_output_aggregate_utf8_bound_applies_before_delivery(monkeypatch):
    body = response()
    body["output"][0]["parts"] = [{"content": "ą" * 10_000}] * 4
    transport(monkeypatch, lambda _: httpx.Response(200, json=body))
    with pytest.raises(RuntimeError, match="ACP agent unavailable"):
        await provider().call("acp.peer", INPUT, IDENTITY)


def test_request_cannot_override_endpoint_or_wire_agent():
    for field in ("base_url", "agent_name", "headers", "session_id"):
        with pytest.raises(ValueError):
            provider().validate(
                "acp.peer", INPUT | {field: "untrusted"}, IDENTITY
            )
