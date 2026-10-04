"""Saved semantic suites use real management routes and explicit scanner fixtures."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from fastfence.app.interfaces.http.semantic_suite_store import SuiteStorageError
from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import Assessment
from tests.fixtures.semantic_suites import suite_cases, suite_rule


def headers(tokens, name="security-admin"):
    return {"Authorization": "Bearer " + tokens[name]}


def review_payload(version=1, identifier="topic"):
    return {
        "base_version": version,
        "rule": suite_rule(identifier).model_dump(),
        "cases": [case.model_dump() for case in suite_cases()],
    }


def scanner(app):
    async def assess(text, _):
        return Assessment(score=1 if "restricted" in text else 0, tokens=10)

    fake = AsyncMock(side_effect=assess)
    app.state.engine.scanner.assess = fake
    return fake


def activate(client, tokens, version=1, identifier="topic"):
    reviewed = client.post(
        "/api/admin/semantic/review",
        headers=headers(tokens),
        json=review_payload(version, identifier),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["tests_passed"] is True, reviewed.text
    response = client.post(
        "/api/admin/semantic/activate",
        headers=headers(tokens),
        json={
            "review_id": reviewed.json()["review_id"],
            "base_version": version,
            "confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def saved(client, tokens):
    response = client.get("/api/admin/semantic/tests", headers=headers(tokens))
    assert response.status_code == 200, response.text
    return response.json()


def replay(client, tokens, state):
    return client.post(
        "/api/admin/semantic/tests/replay",
        headers=headers(tokens),
        json={
            "base_version": state["policy_version"],
            "suite_digest": state["suite_digest"],
        },
    )


@pytest.mark.parametrize("name,status", [(None, 401), ("analyst-blue", 403)])
def test_saved_suites_are_management_only(client, tokens, app, name, status):
    fake = scanner(app)
    auth = headers(tokens, name) if name else {}
    assert (
        client.get("/api/admin/semantic/tests", headers=auth).status_code
        == status
    )
    assert (
        client.post(
            "/api/admin/semantic/tests/replay", headers=auth, content=b"invalid"
        ).status_code
        == status
    )
    fake.assert_not_awaited()


def test_review_activate_private_save_and_replay_without_business_calls(
    client, app, tokens, project
):
    fake = scanner(app)
    app.state.engine.models.complete = AsyncMock(
        side_effect=AssertionError("Business model called")
    )
    result = activate(client, tokens)
    assert result["tests_saved"] is True
    path = project / "config/semantic-policy-tests.yaml"
    assert path.stat().st_mode & 0o777 == 0o600
    state = saved(client, tokens)
    assert state["suites"][0]["status"] == "current"
    assert state["suites"][0]["cases"][0]["text"] == suite_cases()[0].text
    before = (project / "config/policy.yaml").read_bytes(), path.read_bytes()
    fake.reset_mock()
    response = replay(client, tokens, state)
    assert response.status_code == 200
    body = response.json()
    assert body["tests_passed"] and len(body["results"]) == 2
    assert [row["rule_id"] for row in body["results"]] == ["topic", "topic"]
    assert fake.await_count == 2
    assert "Synthetic restricted topic" not in response.text
    assert before == (
        (project / "config/policy.yaml").read_bytes(),
        path.read_bytes(),
    )
    assert "Synthetic restricted topic" not in str(app.state.runtime.audit())
    app.state.engine.models.complete.assert_not_awaited()


def test_changed_source_digest_conflicts_before_any_inference(
    client, tokens, app, project
):
    fake = scanner(app)
    activate(client, tokens)
    state = saved(client, tokens)
    path = project / "config/semantic-policy-tests.yaml"
    path.write_bytes(path.read_bytes() + b"\n# externally edited\n")
    fake.reset_mock()
    assert replay(client, tokens, state).status_code == 409
    fake.assert_not_awaited()


@pytest.mark.parametrize("change", ["remove", "scope"])
def test_inactive_or_changed_scope_is_never_a_false_pass(
    client, tokens, app, change
):
    fake = scanner(app)
    activate(client, tokens)
    policy = app.state.runtime.snapshot().policy.model_dump(mode="json")
    policy["version"] += 1
    if change == "remove":
        policy["semantic"]["rules"] = []
    else:
        policy["semantic"]["rules"][0]["direction"] = "output"
        policy["semantic"]["scan_output"] = True
    assert (
        client.put(
            "/api/admin/policy", headers=headers(tokens), json=policy
        ).status_code
        == 200
    )
    state = saved(client, tokens)
    fake.reset_mock()
    result = replay(client, tokens, state).json()
    assert result["tests_passed"] is False
    if change == "remove":
        assert result["skipped"] == [
            {"rule_id": "topic", "reason": "inactive_rule"}
        ]
        assert result["results"] == []
    else:
        assert all(
            row["reason"] == "scope_changed" and not row["passed"]
            for row in result["results"]
        )
    fake.assert_not_awaited()


def test_model_failure_is_private_and_cannot_pass(client, tokens, app):
    scanner(app)
    activate(client, tokens)
    app.state.engine.scanner.assess = AsyncMock(
        side_effect=ModelUnavailableError("PRIVATE_SCANNER_DIAGNOSTIC")
    )
    response = replay(client, tokens, saved(client, tokens))
    assert response.status_code == 200 and not response.json()["tests_passed"]
    assert all(row["status"] == "error" for row in response.json()["results"])
    assert "PRIVATE_SCANNER" not in response.text


def test_shared_busy_gate_and_deadline_do_not_activate(
    client, tokens, app, monkeypatch
):
    scanner(app)
    activate(client, tokens)
    state = saved(client, tokens)
    session = app.state.semantic_review
    session._busy = True
    assert replay(client, tokens, state).status_code == 429
    session._busy = False
    monkeypatch.setattr(
        "fastfence.app.interfaces.http.semantic_review_session.REVIEW_DEADLINE_SECONDS",
        0.01,
    )

    async def slow(*_):
        await asyncio.sleep(1)
        return Assessment(score=0, tokens=10)

    app.state.engine.scanner.assess = slow
    assert replay(client, tokens, state).status_code == 503
    assert not session._busy
    assert app.state.runtime.snapshot().policy.version == 2


def test_other_rule_saved_regression_failure_blocks_new_activation(
    client, tokens, app
):
    scanner(app)
    activate(client, tokens, identifier="original")

    async def regressed(text, config):
        edited = any(rule.id == "addition" for rule in config.rules)
        failed_original = edited and text == suite_cases()[0].text
        return Assessment(
            score=0 if failed_original else int("restricted" in text), tokens=10
        )

    app.state.engine.scanner.assess = regressed
    payload = review_payload(2, "addition")
    for case in payload["cases"]:
        case["text"] = "New " + case["text"]
    response = client.post(
        "/api/admin/semantic/review",
        headers=headers(tokens),
        json=payload,
    )
    assert response.status_code == 200
    result = response.json()
    original = [row for row in result["cases"] if row["rule_id"] == "original"]
    assert len(original) == 2 and any(not row["passed"] for row in original)
    assert all(
        row["passed"] for row in result["cases"] if row["rule_id"] == "addition"
    )
    assert not result["tests_passed"] and result["review_id"] is None
    assert app.state.runtime.snapshot().policy.version == 2


def test_failed_postactivation_save_explicitly_reports_activated_policy(
    client, tokens, app, monkeypatch
):
    scanner(app)

    def fail(_):
        raise SuiteStorageError("PRIVATE_STORAGE_DIAGNOSTIC")

    monkeypatch.setattr(app.state.semantic_review.store, "commit", fail)
    result = activate(client, tokens)
    assert result["policy_version"] == 2 and result["tests_saved"] is False
    assert result["warnings"] and "PRIVATE_STORAGE" not in str(result)
    assert app.state.runtime.snapshot().policy.version == 2


def test_file_change_during_replay_returns_conflict_without_mutation(
    client, tokens, app, project
):
    scanner(app)
    activate(client, tokens)
    state = saved(client, tokens)
    path = project / "config/semantic-policy-tests.yaml"

    async def changed(*_):
        path.write_bytes(path.read_bytes() + b"\n# operator edit\n")
        return Assessment(score=0, tokens=10)

    app.state.engine.scanner.assess = changed
    assert replay(client, tokens, state).status_code == 409
    assert b"# operator edit" in path.read_bytes()


def test_external_edit_after_policy_publication_preserves_file(
    client, tokens, app, project, monkeypatch
):
    scanner(app)
    activate(client, tokens)
    path = project / "config/semantic-policy-tests.yaml"
    external = path.read_bytes() + b"\n# concurrent operator edit\n"
    original = app.state.runtime.save_policy

    def save_then_edit(*args, **kwargs):
        snapshot = original(*args, **kwargs)
        path.write_bytes(external)
        return snapshot

    monkeypatch.setattr(app.state.runtime, "save_policy", save_then_edit)
    result = activate(client, tokens, version=2, identifier="addition")
    assert result["policy_version"] == 3 and result["tests_saved"] is False
    assert result["warnings"] == ["semantic_tests_not_saved"]
    assert path.read_bytes() == external
    assert app.state.runtime.snapshot().policy.version == 3
    assert not list(path.parent.glob(".semantic-tests-*"))


def test_legacy_rules_can_acquire_suites_one_at_a_time(client, tokens, app):
    scanner(app)
    policy = app.state.runtime.snapshot().policy.model_dump(mode="json")
    policy["version"] = 2
    policy["semantic"].update(
        provider="laya",
        model="qwen3:4b",
        rules=[
            suite_rule("first").model_dump(),
            suite_rule("second").model_dump(),
        ],
    )
    assert (
        client.put(
            "/api/admin/policy", headers=headers(tokens), json=policy
        ).status_code
        == 200
    )
    reviewed = client.post(
        "/api/admin/semantic/review",
        headers=headers(tokens),
        json=review_payload(2, "first"),
    ).json()
    assert reviewed["tests_passed"] and reviewed["review_id"]
    assert any(
        "second: untested_rule" in warning for warning in reviewed["warnings"]
    )
    assert reviewed["missing_rules"] == []
    assert client.post(
        "/api/admin/semantic/activate",
        headers=headers(tokens),
        json={
            "review_id": reviewed["review_id"],
            "base_version": 2,
            "confirmed": True,
        },
    ).json()["tests_saved"]
    result = activate(client, tokens, version=3, identifier="second")
    assert result["tests_saved"]
    state = saved(client, tokens)
    assert {suite["rule"]["id"] for suite in state["suites"]} == {
        "first",
        "second",
    }


def test_malformed_private_file_returns_static_management_error(
    client, tokens, app, project
):
    fake = scanner(app)
    path = project / "config/semantic-policy-tests.yaml"
    path.write_text("PRIVATE_ORIGINAL: [invalid")
    path.chmod(0o600)
    result = client.get("/api/admin/semantic/tests", headers=headers(tokens))
    assert result.status_code == 409 and "PRIVATE_ORIGINAL" not in result.text
    fake.assert_not_awaited()


def test_contradictory_other_rule_expectations_fail_before_inference(
    client, tokens, app, project
):
    fake = scanner(app)
    activate(client, tokens, identifier="original")
    before = (project / "config/semantic-policy-tests.yaml").read_bytes()
    payload = review_payload(2, "addition")
    payload["cases"][0]["expected"] = "no_semantic_block"
    payload["cases"][1]["expected"] = "blocked"
    fake.reset_mock()
    response = client.post(
        "/api/admin/semantic/review", headers=headers(tokens), json=payload
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "semantic_suite_unavailable"
    fake.assert_not_awaited()
    assert app.state.runtime.snapshot().policy.version == 2
    assert (
        project / "config/semantic-policy-tests.yaml"
    ).read_bytes() == before


def test_same_expected_text_across_rules_is_kept_for_provenance(
    client, tokens, app
):
    fake = scanner(app)
    activate(client, tokens, identifier="original")
    fake.reset_mock()
    response = client.post(
        "/api/admin/semantic/review",
        headers=headers(tokens),
        json=review_payload(2, "addition"),
    )
    assert response.status_code == 200 and response.json()["tests_passed"]
    assert {row["rule_id"] for row in response.json()["cases"]} == {
        "original",
        "addition",
    }
    assert fake.await_count == 8
