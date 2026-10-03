"""Actual management transport with explicit scanner fixtures; no live inference."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import Assessment


def payload(**overrides):
    return {
        "base_version": 1,
        "rule": {
            "id": "full-name",
            "instruction": "Block personal full names; company names are permitted.",
            "direction": "input",
            "target": "model",
        },
        "text": "Private example content",
        "direction": "input",
        "target": "model",
        **overrides,
    }


def headers(tokens, identity="security-admin"):
    return {"Authorization": "Bearer " + tokens[identity]}


@pytest.mark.parametrize("identity,code", [(None, 401), ("analyst-blue", 403)])
def test_preview_rejects_unauthorized_before_scanner(
    client, app, tokens, identity, code
):
    scanner = AsyncMock(return_value=Assessment(score=0, tokens=20))
    app.state.engine.scanner.assess = scanner
    response = client.post(
        "/api/admin/semantic/preview",
        headers=headers(tokens, identity) if identity else {},
        json=payload(),
    )
    assert response.status_code == code
    scanner.assert_not_awaited()


@pytest.mark.parametrize(
    "direction,target,applied",
    [
        ("input", "model", True),
        ("output", "model", False),
        ("input", "tool", False),
    ],
)
def test_preview_uses_scope_and_does_not_activate(
    client, app, tokens, project, direction, target, applied
):
    scanner = AsyncMock(return_value=Assessment(score=1, tokens=20))
    app.state.engine.scanner.assess = scanner
    source = project / "config/policy.yaml"
    before = source.read_bytes()
    response = client.post(
        "/api/admin/semantic/preview",
        headers=headers(tokens),
        json=payload(direction=direction, target=target),
    )
    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "blocked"
    assert result["rule_applied"] is applied
    assert result["provider"] == "laya" and result["model"] == "qwen3:4b"
    assert result["base_version"] == 1
    text, config = scanner.await_args.args
    assert text == payload()["text"]
    assert len(config.rules) == int(applied)
    assert config.provider == "laya"
    assert source.read_bytes() == before
    assert app.state.engine.policies.snapshot().policy.version == 1
    assert app.state.engine.ledger.audit() == []
    assert payload()["text"] not in response.text


def test_preview_no_semantic_block_is_not_full_runtime_allow(
    client, app, tokens
):
    app.state.engine.scanner.assess = AsyncMock(
        return_value=Assessment(score=0, tokens=20)
    )
    response = client.post(
        "/api/admin/semantic/preview", headers=headers(tokens), json=payload()
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "no_semantic_block"


@pytest.mark.parametrize(
    "override,code",
    [
        ({"base_version": 2}, 409),
        ({"text": "x" * 4097}, 422),
        ({"target": "all"}, 422),
    ],
)
def test_stale_or_invalid_preview_never_calls_model(
    client, app, tokens, override, code
):
    scanner = AsyncMock(return_value=Assessment(score=0, tokens=20))
    app.state.engine.scanner.assess = scanner
    response = client.post(
        "/api/admin/semantic/preview",
        headers=headers(tokens),
        json=payload(**override),
    )
    assert response.status_code == code
    scanner.assert_not_awaited()


def test_preview_failure_is_private_and_never_activates(
    client, app, tokens, project
):
    source = project / "config/policy.yaml"
    before = source.read_bytes()
    app.state.engine.scanner.assess = AsyncMock(
        side_effect=ModelUnavailableError("PRIVATE_UPSTREAM_DIAGNOSTIC")
    )
    response = client.post(
        "/api/admin/semantic/preview", headers=headers(tokens), json=payload()
    )
    assert response.status_code == 503
    assert "PRIVATE_UPSTREAM_DIAGNOSTIC" not in response.text
    assert source.read_bytes() == before


def test_preview_deadline_returns_unavailable(client, app, tokens):
    policy = app.state.engine.policies.snapshot().policy.model_dump(mode="json")
    policy["version"] += 1
    policy["semantic"].update(provider="laya", model="qwen3:4b", timeout_ms=100)
    assert (
        client.put(
            "/api/admin/policy", headers=headers(tokens), json=policy
        ).status_code
        == 200
    )

    async def slow(*_):
        await asyncio.sleep(5)
        return Assessment(score=0, tokens=20)

    app.state.engine.scanner.assess = slow
    response = client.post(
        "/api/admin/semantic/preview",
        headers=headers(tokens),
        json=payload(base_version=2),
    )
    assert response.status_code == 503
    assert app.state.engine.policies.snapshot().policy.version == 2
