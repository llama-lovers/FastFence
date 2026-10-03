from __future__ import annotations

import pytest

from tests.fixtures.auth import headers


def text_rule(**overrides):
    return {
        "id": "preview-restriction",
        "operator": "word_contains",
        "value": "a",
        **overrides,
    }


@pytest.mark.parametrize("endpoint", ["schema", "preview"])
def test_rule_authoring_requires_management_identity(client, tokens, endpoint):
    request = client.get if endpoint == "schema" else client.post
    options = (
        {}
        if endpoint == "schema"
        else {"json": {"rule": text_rule(), "samples": ["data"]}}
    )
    path = f"/api/admin/rules/{endpoint}"
    assert request(path, **options).status_code == 401
    assert request(path, headers=headers(tokens), **options).status_code == 403
    assert (
        request(
            path, headers=headers(tokens, "security-admin"), **options
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    ("rule", "samples", "expected"),
    [
        (
            text_rule(),
            ["tiny report", "DATA", "ą", chr(0xFF21), "1a2"],
            [False, True, False, True, True],
        ),
        (text_rule(value="ab"), ["a-b", "xabx", "1ab2"], [False, True, True]),
        (
            text_rule(operator="contains", value="-"),
            ["a-b", "ab"],
            [True, False],
        ),
        (
            text_rule(operator="equals", value="report"),
            ["REPORT", "report.", " report"],
            [True, False, False],
        ),
        (
            text_rule(value="A", case_sensitive=True),
            ["A", "a", chr(0xFF21)],
            [True, False, True],
        ),
    ],
)
def test_preview_is_pure_validated_matching_without_policy_or_execution_side_effects(
    client, tokens, app, monkeypatch, rule, samples, expected
):
    before = app.state.engine.policies.snapshot()

    async def forbidden(*args, **kwargs):
        pytest.fail("Rule preview executed an upstream or semantic model")

    monkeypatch.setattr(app.state.engine.models, "complete", forbidden)
    monkeypatch.setattr(app.state.engine.tools, "call", forbidden)
    monkeypatch.setattr(app.state.engine.scanner, "assess", forbidden)
    response = client.post(
        "/api/admin/rules/preview",
        headers=headers(tokens, "security-admin"),
        json={"rule": rule, "samples": samples},
    )
    assert response.status_code == 200, response.text
    assert response.json()["matches"] == expected
    assert response.json()["rule"]["id"] == rule["id"]
    assert app.state.engine.policies.snapshot() is before
    assert app.state.engine.ledger.stats()["requests"] == 0


def test_schema_exposes_bounded_rule_contract(client, tokens):
    response = client.get(
        "/api/admin/rules/schema", headers=headers(tokens, "security-admin")
    )
    assert response.status_code == 200
    properties = response.json()["properties"]
    assert set(properties["operator"]["enum"]) == {
        "contains",
        "word_contains",
        "equals",
    }
    assert properties["value"]["maxLength"] == 128
    assert properties["target"]["default"] == "model"


def test_invalid_preview_is_sanitized_and_does_not_activate_rule(
    client, tokens, app
):
    before = app.state.engine.policies.snapshot()
    response = client.post(
        "/api/admin/rules/preview",
        headers=headers(tokens, "security-admin"),
        json={
            "rule": text_rule(operator="invalid-private-marker"),
            "samples": ["private-sample"],
        },
    )
    assert response.status_code == 422
    assert "invalid-private-marker" not in response.text
    assert "private-sample" not in response.text
    assert app.state.engine.policies.snapshot() is before


@pytest.mark.parametrize("samples", [["text"] * 17, ["a" * 4097]])
def test_preview_sample_limits_reject_oversized_batches(
    client, tokens, samples
):
    response = client.post(
        "/api/admin/rules/preview",
        headers=headers(tokens, "security-admin"),
        json={"rule": text_rule(), "samples": samples},
    )
    assert response.status_code == 422
