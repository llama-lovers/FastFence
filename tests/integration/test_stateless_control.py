import base64
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fastfence.app.factory import create_app
from fastfence.shared.settings.app_settings import AppSettings
from tests.fixtures.auth import headers
from tests.fixtures.policy import configure_policy


@pytest.fixture
def stateless(project, monkeypatch):
    app = create_app(
        AppSettings(
            root=project,
            state=project / "state",
            ollama_url="http://127.0.0.1:1",
            kev_url="http://127.0.0.1:1",
            anonymization_keys_json=SecretStr(
                json.dumps(
                    {"test": base64.b64encode(bytes(range(32))).decode()}
                )
            ),
            anonymization_key_id="test",
        )
    )
    calls = []

    async def echo(
        model, prompt, max_tokens, timeout_ms, stop=None, messages=None
    ):
        calls.append({"prompt": prompt, "messages": messages})
        return {
            "text": prompt if messages is None else messages[-1].content,
            "finish_reason": "stop",
        }, 4

    monkeypatch.setattr(app.state.engine.models, "complete", echo)

    def enable(data):
        data["privacy"].update(input="redact", output="redact")
        data["anonymization"] = {
            "enabled": True,
            "mode": "reversible",
            "rules": [
                {
                    "id": "email",
                    "operator": "regex",
                    "value": "[A-Za-z]+@example[.]org",
                    "replacement": "EMAIL",
                    "allow_restore": True,
                }
            ],
        }

    configure_policy(app.state.engine, enable)
    with TestClient(app) as client:
        yield app, client, calls


def complete(client, tokens, prompt="anna@example.org", **overrides):
    actor = overrides.pop("actor", "analyst-blue")
    return client.post(
        "/api/models/complete",
        headers=headers(tokens, actor),
        json={"model": "qwen3:0.6b", "prompt": prompt, **overrides},
    ).json()


def test_default_echo_protects_upstream_and_audit_without_returning_original(
    stateless, tokens
):
    app, client, calls = stateless
    verdict = complete(client, tokens)
    assert (
        verdict["decision"] in {"allowed", "redacted"}
        and verdict["upstream_executed"]
    )
    token = verdict["output"]["text"]
    assert token.startswith("[FFR1.") and "anna@example.org" not in token
    assert calls == [{"prompt": token, "messages": None}]
    assert verdict["anonymized"] and not verdict["restored"]
    audit = client.get(
        "/api/admin/audit.jsonl", headers=headers(tokens, "security-admin")
    ).text
    assert "anna@example.org" not in audit and token not in audit
    assert (
        next(
            row
            for row in app.state.engine.ledger.budgets()
            if row["subject"] == "analyst-blue"
        )["inflight"]
        == 0
    )


def test_exact_token_restoration_is_explicit_and_never_sent_upstream(
    stateless, tokens
):
    _, client, calls = stateless
    verdict = complete(client, tokens, restore_originals=True)
    assert (
        verdict["output"]["text"] == "anna@example.org" and verdict["restored"]
    )
    assert calls[0]["prompt"].startswith("[FFR1.")
    assert "anna@example.org" not in json.dumps(calls)


@pytest.mark.parametrize("block", ["privacy", "text_rule"])
def test_previous_valid_token_cannot_bypass_new_input_hard_block(
    stateless, tokens, block
):
    app, client, calls = stateless
    token = complete(client, tokens)["output"]["text"]

    def restrict(data):
        if block == "privacy":
            data["privacy"]["input"] = "block"
        else:
            data["text_rules"] = [
                {
                    "id": "deny_name",
                    "operator": "contains",
                    "value": "anna",
                    "direction": "input",
                    "target": "model",
                }
            ]

    configure_policy(app.state.engine, restrict)
    denied = complete(client, tokens, token)
    assert denied["decision"] == "blocked" and not denied["upstream_executed"]
    assert denied["reason"] == (
        "input_sensitive_data" if block == "privacy" else "input_text_rule"
    )
    assert len(calls) == 1


def test_token_owner_is_trusted_credential_not_client_headers(
    stateless, tokens
):
    _, client, calls = stateless
    token = complete(client, tokens)["output"]["text"]
    denied = complete(client, tokens, token, actor="analyst-green")
    assert (
        denied["reason"] == "anonymization_invalid_token"
        and not denied["upstream_executed"]
    )
    assert len(calls) == 1


def test_original_privacy_block_is_preserved_before_masking(stateless, tokens):
    app, client, calls = stateless
    configure_policy(
        app.state.engine, lambda data: data["privacy"].update(input="block")
    )
    denied = complete(client, tokens)
    assert (
        denied["reason"] == "input_sensitive_data"
        and not denied["upstream_executed"]
    )
    assert calls == []


def test_revoked_restoration_permission_blocks_opt_in(stateless, tokens):
    app, client, calls = stateless
    configure_policy(
        app.state.engine,
        lambda data: data["anonymization"]["rules"][0].update(
            allow_restore=False
        ),
    )
    denied = complete(client, tokens, restore_originals=True)
    assert (
        denied["reason"] == "anonymization_restore_denied"
        and not denied["upstream_executed"]
    )
    assert calls == []


def test_native_chat_preserves_roles_and_masks_only_content(stateless, tokens):
    _, client, calls = stateless
    verdict = complete(
        client,
        tokens,
        prompt="",
        messages=[
            {"role": "system", "content": "Repeat exactly"},
            {"role": "user", "content": "anna@example.org"},
        ],
    )
    assert verdict["upstream_executed"] and verdict["output"][
        "text"
    ].startswith("[FFR1.")
    messages = calls[0]["messages"]
    assert [message.role for message in messages] == ["system", "user"]
    assert messages[0].content == "Repeat exactly"
    assert "anna@example.org" not in messages[1].content


@pytest.mark.parametrize("restore", [False, True])
def test_openai_restoration_requires_exact_explicit_header(
    stateless, tokens, restore
):
    _, client, calls = stateless
    response = client.post(
        "/v1/chat/completions",
        headers={
            **headers(tokens),
            "X-FastFence-Restore-Originals": str(restore).lower(),
        },
        json={
            "model": "qwen3:0.6b",
            "messages": [{"role": "user", "content": "anna@example.org"}],
        },
    )
    assert response.status_code == 200
    result = response.json()
    text = result["choices"][0]["message"]["content"]
    assert (text == "anna@example.org") == restore
    assert result["fastfence"]["restored"] == restore
    assert "anna@example.org" not in calls[0]["messages"][0].content


@pytest.mark.parametrize("restore", [False, True])
def test_mcp_completion_uses_same_restore_permission_and_control_pipeline(
    stateless, tokens, restore
):
    _, client, calls = stateless
    response = client.post(
        "/mcp/",
        headers={
            **headers(tokens),
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "complete",
                "arguments": {
                    "model": "qwen3:0.6b",
                    "prompt": "anna@example.org",
                    "restore_originals": restore,
                },
            },
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]["structuredContent"]
    assert result["upstream_executed"] and result["restored"] == restore
    assert (result["output"]["text"] == "anna@example.org") == restore
    assert calls[0]["prompt"].startswith("[FFR1.")
    assert "anna@example.org" not in calls[0]["prompt"]
