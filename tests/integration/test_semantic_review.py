"""Reviewed semantic activation is owner-bound, snapshot-bound and fail-closed."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from fastfence.app.interfaces.http import semantic_review_session as sessions
from fastfence.app.interfaces.http.semantic_review_models import (
    SemanticActivateRequest,
    SemanticReviewError,
    SemanticReviewRequest,
)
from fastfence.modules.control.domain.models import Assessment, Identity
from tests.fixtures.auth import headers
from tests.fixtures.policy import configure_policy


def payload(version=1):
    return {
        "base_version": version,
        "rule": {
            "id": "topics",
            "instruction": "Block forbidden topics.",
            "direction": "input",
            "target": "model",
        },
        "cases": [
            {
                "id": "deny",
                "text": "forbidden",
                "direction": "input",
                "target": "model",
                "expected": "blocked",
            },
            {
                "id": "allow",
                "text": "Hello",
                "direction": "input",
                "target": "model",
                "expected": "no_semantic_block",
            },
        ],
    }


@pytest.fixture
def classifier(app, monkeypatch):
    calls = []

    async def assess(text, config):
        calls.append((text, config))
        return Assessment(score=1 if text == "forbidden" else 0, tokens=10)

    monkeypatch.setattr(app.state.engine.scanner, "assess", assess)
    business = AsyncMock(
        side_effect=AssertionError("review must not execute business work")
    )
    monkeypatch.setattr(app.state.engine.models, "complete", business)
    return calls, business


def review(client, tokens, data=None):
    return client.post(
        "/api/admin/semantic/review",
        headers=headers(tokens, "security-admin"),
        json=data or payload(),
    )


def activate(client, tokens, reviewed, **updates):
    return client.post(
        "/api/admin/semantic/activate",
        headers=headers(tokens, "security-admin"),
        json={
            "review_id": reviewed["review_id"],
            "base_version": reviewed["base_version"],
            "confirmed": True,
            **updates,
        },
    )


def test_review_then_exact_one_use_activation(client, app, tokens, classifier):
    before = app.state.engine.policies.policy_path.read_bytes()
    response = review(client, tokens)
    assert response.status_code == 200
    data = response.json()
    assert data["tests_passed"] and data["review_id"]
    assert data["scope"] == "semantic_only" and data["model"] == "qwen3:4b"
    assert [row["before"]["status"] for row in data["cases"]] == [
        "not_evaluated"
    ] * 2
    assert all(
        row["passed"] and row["rule_id"] == "topics" for row in data["cases"]
    )
    assert "version: 2" in data["yaml_diff"]
    assert app.state.engine.policies.policy_path.read_bytes() == before
    assert app.state.engine.ledger.budgets() == []
    assert app.state.engine.ledger.stats()["requests"] == 0
    classifier[1].assert_not_awaited()
    receipt = app.state.semantic_review._receipts[data["review_id"]]
    result = activate(client, tokens, data)
    assert result.status_code == 200 and result.json()["tests_saved"]
    assert app.state.engine.policies.snapshot().policy == receipt.candidate
    assert len(classifier[0]) == 2  # Activation performs no inference.
    assert activate(client, tokens, data).status_code == 404


@pytest.mark.parametrize("actor,status", [(None, 401), ("analyst-blue", 403)])
def test_management_auth_precedes_review_and_activation(
    client, tokens, classifier, actor, status
):
    auth = {} if actor is None else headers(tokens, actor)
    for path in ("review", "activate"):
        response = client.post(
            "/api/admin/semantic/" + path, headers=auth, json={}
        )
        assert response.status_code == status
    assert classifier[0] == []


@pytest.mark.parametrize(
    "mode",
    [
        "missing_expectation",
        "duplicate",
        "outside_scope",
        "expanded_scope",
        "too_many",
        "blank",
        "boolean_version",
    ],
)
def test_invalid_or_incomplete_case_coverage_rejected(
    client, tokens, classifier, mode
):
    data = payload()
    if mode == "missing_expectation":
        data["cases"][1]["expected"] = "blocked"
    if mode == "duplicate":
        data["cases"][1]["id"] = "deny"
    if mode == "outside_scope":
        data["cases"][1]["direction"] = "output"
    if mode == "expanded_scope":
        data["rule"].update(direction="both", target="all")
    if mode == "too_many":
        data["cases"] *= 9
    if mode == "blank":
        data["cases"][0]["text"] = ""
    if mode == "boolean_version":
        data["base_version"] = True
    assert review(client, tokens, data).status_code == 422
    assert classifier[0] == []


@pytest.mark.parametrize(
    "failure", ["wrong_decision", "provider_error", "timeout"]
)
def test_failed_case_returns_details_without_receipt(
    client, app, tokens, monkeypatch, failure
):
    async def fail(text, config):
        if failure == "provider_error":
            raise RuntimeError("SYNTHETIC_PRIVATE_ERROR")
        if failure == "timeout":
            raise TimeoutError("SYNTHETIC_PRIVATE_ERROR")
        return Assessment(score=0, tokens=1)

    monkeypatch.setattr(app.state.engine.scanner, "assess", fail)
    response = review(client, tokens)
    assert response.status_code == 200
    assert (
        not response.json()["tests_passed"]
        and response.json()["review_id"] is None
    )
    assert "SYNTHETIC_PRIVATE_ERROR" not in response.text
    assert app.state.engine.policies.snapshot().policy.version == 1
    assert app.state.semantic_review._receipts == {}


@pytest.mark.parametrize(
    "mutation",
    ["active_policy", "source_policy", "source_feed_same_version", "suite"],
)
def test_changed_snapshot_or_suite_prevents_activation(
    client, app, project, tokens, classifier, mutation
):
    result = review(client, tokens).json()
    if mutation == "active_policy":
        configure_policy(
            app.state.engine, lambda data: data.update(description="new state")
        )
    elif mutation == "source_policy":
        path = project / "config/policy.yaml"
        path.write_text(path.read_text().replace("version: 1", "version: 2"))
    elif mutation == "source_feed_same_version":
        path = project / "config/signatures.json"
        feed = json.loads(path.read_text())
        feed["signatures"] = []
        path.write_text(json.dumps(feed))
    else:
        path = project / "config/semantic-policy-tests.yaml"
        path.write_text("schema_version: 1\nsuites: []\n")
        path.chmod(0o600)
    source_before = (project / "config/policy.yaml").read_bytes()
    assert activate(client, tokens, result).status_code == 409
    assert (project / "config/policy.yaml").read_bytes() == source_before


@pytest.mark.parametrize("confirmed", [False, 1, "true", None])
def test_confirmation_is_explicit_and_cannot_carry_modified_candidate(
    client, tokens, classifier, confirmed
):
    result = review(client, tokens).json()
    assert (
        activate(client, tokens, result, confirmed=confirmed).status_code == 422
    )
    assert activate(client, tokens, result, candidate={}).status_code == 422


def test_receipt_is_owner_and_tenant_bound_and_expires(
    client, app, tokens, classifier, monkeypatch
):
    data = review(client, tokens).json()
    session = app.state.semantic_review
    receipt = session._receipts[data["review_id"]]
    request = SemanticActivateRequest(
        review_id=data["review_id"], base_version=1, confirmed=True
    )
    for subject, tenant in (
        ("other", receipt.tenant),
        (receipt.subject, "other"),
    ):
        with pytest.raises(SemanticReviewError, match="not_found"):
            session.activate(
                request,
                Identity(
                    subject=subject, tenant=tenant, roles=["admin"], admin=True
                ),
            )
    monkeypatch.setattr(
        sessions.time, "monotonic", lambda: receipt.expires_monotonic + 1
    )
    with pytest.raises(SemanticReviewError, match="expired"):
        session.activate(
            request,
            Identity(
                subject=receipt.subject,
                tenant=receipt.tenant,
                roles=["admin"],
                admin=True,
            ),
        )


async def test_singleflight_cancellation_and_total_deadline(
    app, tokens, monkeypatch
):
    session = app.state.semantic_review
    admin = app.state.identities.authenticate(tokens["security-admin"])
    entered = asyncio.Event()

    async def slow(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(app.state.engine.scanner, "assess", slow)
    request = SemanticReviewRequest.model_validate(payload())
    first = asyncio.create_task(session.review(request, admin))
    await entered.wait()
    with pytest.raises(SemanticReviewError, match="busy"):
        await session.review(request, admin)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not session._busy and not session._receipts
    monkeypatch.setattr(sessions, "REVIEW_DEADLINE_SECONDS", 0.01)
    result = await session.review(request, admin)
    assert not result.tests_passed and result.review_id is None
    assert len(result.cases) == 2
    assert all(
        row.after.reason == "semantic_review_deadline_exceeded"
        for row in result.cases
    )
    assert not session._busy


def test_receipts_are_bounded_before_additional_inference(
    client, app, tokens, classifier, monkeypatch
):
    monkeypatch.setattr(sessions, "MAX_RECEIPTS", 1)
    assert review(client, tokens).json()["tests_passed"]
    assert review(client, tokens).status_code == 429
    assert len(classifier[0]) == 2


@pytest.mark.parametrize("text", [" \n\t", "\ud800", "Hello", "ą" * 2049])
def test_whitespace_unicode_and_contradictory_examples_are_private_422(
    client, tokens, classifier, text
):
    data = payload()
    data["cases"][0]["text"] = text
    response = client.post(
        "/api/admin/semantic/review",
        headers={
            **headers(tokens, "security-admin"),
            "Content-Type": "application/json",
        },
        content=json.dumps(data),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request schema"}
    assert classifier[0] == []


async def test_deadline_after_last_case_cannot_issue_receipt(
    app, tokens, classifier, monkeypatch
):
    session = app.state.semantic_review

    @asynccontextmanager
    async def expired_after_result():
        yield
        raise TimeoutError

    monkeypatch.setattr(session, "evaluation_slot", expired_after_result)
    result = await session.review(
        SemanticReviewRequest.model_validate(payload()),
        app.state.identities.authenticate(tokens["security-admin"]),
    )
    assert all(row.passed for row in result.cases)
    assert result.review_id is None and not result.tests_passed
    assert "semantic_review_deadline_exceeded" in result.warnings


def test_output_review_enables_output_and_retains_configuration(
    client, app, tokens, classifier
):
    configure_policy(
        app.state.engine,
        lambda data: data["semantic"].update(
            provider="ollama", scan_output=False, threshold=0.9
        ),
    )
    data = payload(version=2)
    data["rule"].update(direction="output", target="tool")
    for case in data["cases"]:
        case.update(direction="output", target="tool")
    result = review(client, tokens, data).json()
    assert result["tests_passed"]
    assert all(
        row["before"]["reason"] == "output_scan_disabled"
        for row in result["cases"]
    )
    candidate = app.state.semantic_review._receipts[
        result["review_id"]
    ].candidate
    assert (
        candidate.semantic.provider == "laya" and candidate.semantic.scan_output
    )
    assert candidate.semantic.timeout_ms == 30_000
    assert candidate.semantic.threshold == 0.9
    assert all(
        config.rules[0].applies_to("output", "tool")
        for _, config in classifier[0]
    )
