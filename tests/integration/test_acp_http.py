"""Native ACP reaches the actual protected tool pipeline and transport adapter."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from fastfence.app.factory import create_app
from fastfence.shared.settings.app_settings import AppSettings
from tests.fixtures.auth import headers
from tests.fixtures.policy import configure_policy


def body(text="hello", **updates):
    return {
        "agent_name": "uppercase",
        "mode": "sync",
        "session_id": None,
        "session": None,
        "input": [
            {
                "role": "user",
                "created_at": datetime.now(UTC).isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "parts": [
                    {
                        "content": text,
                        "content_type": "text/plain",
                        "content_encoding": "plain",
                        "name": None,
                        "content_url": None,
                        "metadata": None,
                    }
                ],
            }
        ],
        **updates,
    }


@pytest.fixture
def acp(project, monkeypatch):
    requests = []
    output = {"text": "HELLO"}

    def provider(request):
        requests.append(json.loads(request.content))
        assert str(request.url) == "http://127.0.0.1:8020/runs"
        assert (
            request.headers["authorization"]
            == "Bearer synthetic-upstream-credential"
        )
        return httpx.Response(
            200,
            json={
                "agent_name": "uppercase",
                "status": "completed",
                "output": [
                    {
                        "role": "agent/uppercase",
                        "parts": [
                            {
                                "content": output["text"],
                                "content_type": "text/plain",
                            }
                        ],
                    }
                ],
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(provider), **kwargs
        ),
    )
    app = create_app(
        AppSettings(
            root=project,
            acp_agents={
                "uppercase": {
                    "base_url": "http://127.0.0.1:8020",
                    "agent_name": "uppercase",
                    "api_key": "synthetic-upstream-credential",  # pragma: allowlist secret
                }
            },
        )
    )
    configure_policy(
        app.state.engine,
        lambda data: data.update(
            tools={
                "acp.uppercase": {"roles": ["analyst"], "timeout_ms": 5000},
            }
        ),
    )
    with TestClient(app) as client:
        yield app, client, requests, output


def test_native_discovery_execution_and_agent_identity(acp, tokens):
    _, client, requests, _ = acp
    auth = headers(tokens)
    assert client.get("/acp/agents").status_code == 401
    assert (
        client.get(
            "/acp/agents", headers=headers(tokens, "security-admin")
        ).status_code
        == 403
    )
    agents = client.get("/acp/agents", headers=auth).json()["agents"]
    assert [item["name"] for item in agents] == ["uppercase"]
    assert client.get("/acp/agents/uppercase", headers=auth).json()[
        "input_content_types"
    ] == ["text/plain"]
    assert client.get("/acp/agents/other", headers=auth).status_code == 404
    response = client.post("/acp/runs", headers=auth, json=body())
    run = response.json()
    assert run["status"] == "completed" and run["error"] is None
    assert run["output"][0]["parts"][0]["content"] == "HELLO"
    assert response.headers["x-fastfence-upstream-executed"] == "true"
    assert requests[0]["input"][0]["parts"][0]["content"] == "hello"
    assert "synthetic-upstream-credential" not in response.text


@pytest.mark.parametrize("direction", ["input", "output"])
def test_letter_rule_ignores_protocol_metadata_but_checks_actual_content(
    acp, tokens, direction
):
    app, client, requests, output = acp
    configure_policy(
        app.state.engine,
        lambda data: data.update(
            text_rules=[
                {
                    "id": "letter-a",
                    "operator": "word_contains",
                    "value": "a",
                    "direction": direction,
                    "target": "tool",
                }
            ]
        ),
    )
    assert (
        client.post(
            "/acp/runs", headers=headers(tokens), json=body("hello")
        ).json()["status"]
        == "completed"
    )
    if direction == "output":
        output["text"] = "CAT"
    response = client.post(
        "/acp/runs", headers=headers(tokens), json=body("cat")
    )
    assert response.json()["status"] == "failed"
    assert response.json()["output"] == []
    assert (
        response.json()["error"]["data"]["reason"] == f"{direction}_text_rule"
    )
    assert len(requests) == (1 if direction == "input" else 2)


def test_redaction_on_both_sides_and_metadata_only_audit(acp, tokens):
    app, client, requests, output = acp
    configure_policy(
        app.state.engine,
        lambda data: data["privacy"].update(input="redact", output="redact"),
    )
    output["text"] = "reply@example.org"
    response = client.post(
        "/acp/runs", headers=headers(tokens), json=body("sender@example.org")
    )
    assert response.json()["status"] == "completed"
    assert "sender@example.org" not in json.dumps(requests)
    assert "reply@example.org" not in response.text
    audit = json.dumps(app.state.runtime.audit())
    assert (
        "sender@example.org" not in audit and "reply@example.org" not in audit
    )


@pytest.mark.parametrize("mode", ["stream", "async"])
def test_unsupported_run_modes_do_not_call_upstream(acp, tokens, mode):
    _, client, requests, _ = acp
    response = client.post(
        "/acp/runs", headers=headers(tokens), json=body(mode=mode)
    )
    assert response.status_code == 422 and not requests


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "00000000-0000-0000-0000-000000000001"),
        ("session", {}),
        ("metadata", {"upstream_url": "http://127.0.0.1"}),
    ],
)
def test_sessions_and_unsupported_fields_rejected(acp, tokens, field, value):
    _, client, requests, _ = acp
    response = client.post(
        "/acp/runs", headers=headers(tokens), json=body(**{field: value})
    )
    assert response.status_code == 422 and not requests


@pytest.mark.parametrize(
    "field,value",
    [
        ("content_type", "image/png"),
        ("content_encoding", "base64"),
        ("content_url", "http://127.0.0.1/private"),
        ("metadata", {"kind": "trajectory"}),
    ],
)
def test_uninspected_parts_rejected_without_fetching(acp, tokens, field, value):
    _, client, requests, _ = acp
    data = body()
    data["input"][0]["parts"][0][field] = value
    assert (
        client.post("/acp/runs", headers=headers(tokens), json=data).status_code
        == 422
    )
    assert not requests


def test_auth_precedes_body_and_bounded_malformed_json_fails_closed(
    acp, tokens
):
    _, client, requests, _ = acp
    assert client.post("/acp/runs", content=b"x" * 70000).status_code == 401
    assert (
        client.post(
            "/acp/runs", headers=headers(tokens), content=b"x" * 70000
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/acp/runs",
            headers=headers(tokens),
            content=b"[" * 2000 + b"0" + b"]" * 2000,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/acp/runs",
            headers=headers(tokens),
            content=b'{"agent_name":"a","agent_name":"uppercase"}',
        ).status_code
        == 422
    )
    assert not requests


def test_no_stored_runs_or_remote_cancel_interface(acp, tokens):
    _, client, requests, _ = acp
    for path in (
        "/acp/runs/id",
        "/acp/runs/id/events",
        "/acp/runs/id/cancel",
        "/acp/sessions/id",
    ):
        assert client.post(path, headers=headers(tokens)).status_code == 501
    assert not requests


def test_same_subject_budget_is_shared_across_native_acp_and_rest(acp, tokens):
    app, client, requests, _ = acp
    configure_policy(
        app.state.engine,
        lambda data: data["budgets"]["analyst"].update(calls=1),
    )
    assert (
        client.post("/acp/runs", headers=headers(tokens), json=body()).json()[
            "status"
        ]
        == "completed"
    )
    denied = client.post(
        "/api/invoke",
        headers=headers(tokens),
        json={
            "tool": "acp.uppercase",
            "arguments": {"input": [{"role": 0, "parts": ["hello"]}]},
        },
    ).json()
    assert denied["reason"] == "budget_calls" and len(requests) == 1
