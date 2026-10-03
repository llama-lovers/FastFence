"""Actual REST controls with real asymmetric crypto and an explicit echo backend."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from examples.docs.asymmetric_keys import generate_pair
from fastfence.app.factory import create_app
from fastfence.shared.settings.app_settings import AppSettings
from tests.fixtures.auth import headers
from tests.fixtures.policy import configure_policy


@pytest.fixture
def asymmetric(project, monkeypatch):
    public, private = generate_pair(project / "rsa")
    app = create_app(
        AppSettings(
            root=project,
            anonymization_keys_json=json.dumps(
                {"local-v1": base64.b64encode(bytes(range(32))).decode()}
            ),
            anonymization_public_key_file=public,
            anonymization_private_key_file=private,
        )
    )
    calls = []

    async def echo(
        model, prompt, max_tokens, timeout_ms, stop=None, messages=None
    ):
        calls.append(prompt)
        return {"text": prompt, "finish_reason": "stop"}, 4

    monkeypatch.setattr(app.state.engine.models, "complete", echo)

    def enable(data):
        data["privacy"].update(input="redact", output="redact")
        data["anonymization"] = {
            "enabled": True,
            "mode": "reversible",
            "rules": [
                {
                    "id": "person",
                    "operator": "literal",
                    "value": "Anna Kowalska",
                    "replacement": "PERSON",
                    "allow_restore": True,
                }
            ],
        }

    configure_policy(app.state.engine, enable)
    with TestClient(app) as client:
        yield app, client, calls


def invoke(
    client, tokens, prompt="Anna Kowalska", actor="analyst-blue", restore=False
):
    response = client.post(
        "/api/models/complete",
        headers=headers(tokens, actor),
        json={
            "model": "qwen3:0.6b",
            "prompt": prompt,
            "max_output_tokens": 16,
            "restore_originals": restore,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_rest_default_hides_original_and_opt_in_restores_without_upstream_leak(
    asymmetric, tokens
):
    _, client, calls = asymmetric
    protected = invoke(client, tokens)
    assert protected["decision"] in {"allowed", "redacted"}
    assert protected["anonymized"] and not protected["restored"]
    token = protected["output"]["text"]
    assert token.startswith("[FFR2.") and calls == [token]
    restored = invoke(client, tokens, restore=True)
    assert (
        restored["restored"] and restored["output"]["text"] == "Anna Kowalska"
    )
    assert all(
        "Anna Kowalska" not in text and text.startswith("[FFR2.")
        for text in calls
    )
    audit = client.get(
        "/api/admin/audit.jsonl", headers=headers(tokens, "security-admin")
    ).text
    assert "Anna Kowalska" not in audit and token not in audit


def test_received_rsa_token_cannot_cross_owner_or_skip_original_hard_blocks(
    asymmetric, tokens
):
    app, client, calls = asymmetric
    token = invoke(client, tokens)["output"]["text"]
    wrong_owner = invoke(client, tokens, token, actor="analyst-green")
    assert wrong_owner["reason"] == "anonymization_invalid_token"
    assert not wrong_owner["upstream_executed"]

    def restrict(data):
        data["text_rules"] = [
            {
                "id": "deny-person",
                "operator": "contains",
                "value": "Anna",
                "direction": "input",
                "target": "model",
            }
        ]

    configure_policy(app.state.engine, restrict)
    denied = invoke(client, tokens, token)
    assert (
        denied["reason"] == "input_text_rule"
        and not denied["upstream_executed"]
    )
    assert len(calls) == 1


def test_rsa_recovery_still_requires_rule_permission(asymmetric, tokens):
    app, client, calls = asymmetric
    configure_policy(
        app.state.engine,
        lambda data: data["anonymization"]["rules"][0].update(
            allow_restore=False
        ),
    )
    verdict = invoke(client, tokens, restore=True)
    assert verdict["reason"] == "anonymization_restore_denied"
    assert not verdict["restored"] and "Anna Kowalska" not in json.dumps(
        verdict
    )
    assert all("Anna Kowalska" not in text for text in calls)
