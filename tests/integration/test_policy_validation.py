"""Invalid control configurations must be rejected before replacing active policy."""

from __future__ import annotations

import json

import pytest

from tests.fixtures.auth import headers


def test_policy_cannot_grant_a_role_without_a_budget(client, tokens):
    admin = headers(tokens, "security-admin")
    original = client.get("/api/admin/status", headers=admin).json()["policy"]
    candidate = {**original, "version": original["version"] + 1}
    candidate["tools"]["knowledge.search"]["roles"].append("unbudgeted")
    response = client.put("/api/admin/policy", headers=admin, json=candidate)
    assert response.status_code == 422
    active = client.get("/api/admin/status", headers=admin).json()["policy"]
    assert active["version"] == original["version"]
    assert "unbudgeted" not in active["tools"]["knowledge.search"]["roles"]
    authorized = client.post(
        "/api/invoke",
        headers=headers(tokens),
        json={"tool": "knowledge.search", "arguments": {"query": "forecast"}},
    )
    assert authorized.json()["decision"] == "allowed"


@pytest.mark.parametrize(
    ("section", "field", "invalid"),
    [
        ("semantic", "threshold", -0.1),
        ("semantic", "threshold", 1.1),
        ("semantic", "provider", "untrusted-http-provider"),
        ("budgets", "tokens", 0),
        ("budgets", "concurrent", 0),
        ("budgets", "cost_microusd", -1),
    ],
)
def test_invalid_policy_limits_cannot_replace_active_snapshot(
    client, tokens, section, field, invalid
):
    admin = headers(tokens, "security-admin")
    original = client.get("/api/admin/status", headers=admin).json()["policy"]
    candidate = json.loads(json.dumps(original))
    candidate["version"] += 1
    settings = candidate[section]
    if section == "budgets":
        settings = settings["analyst"]
    settings[field] = invalid
    response = client.put("/api/admin/policy", headers=admin, json=candidate)
    assert response.status_code == 422
    active = client.get("/api/admin/status", headers=admin).json()["policy"]
    assert active == original
