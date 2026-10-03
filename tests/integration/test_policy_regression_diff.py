"""Real local control inspection with an explicit model-generation fixture."""

import copy
import json

import pytest
import yaml

from fastfence.app.interfaces.http.authoring_regression import (
    SavedRegressionSuite,
    policy_digest,
)
from tests.fixtures.auth import headers
from tests.fixtures.policy import configure_policy

CASES = [
    {
        "label": "match",
        "text": "Cat",
        "target": "model",
        "direction": "input",
        "expected_decision": "blocked",
    },
    {
        "label": "benign",
        "text": "Hello",
        "target": "model",
        "direction": "input",
        "expected_decision": "no_local_match",
    },
    {
        "label": "casefold",
        "text": "CAT",
        "target": "model",
        "direction": "input",
        "expected_decision": "blocked",
    },
    {
        "label": "other-target",
        "text": "Cat",
        "target": "tool",
        "direction": "input",
        "expected_decision": "no_local_match",
    },
]


class GeneratedFixtureAuthor:
    """No inference occurs; live generation is verified separately."""

    def __init__(self):
        self.calls = 0

    async def draft(self, request):
        self.calls += 1
        assert "GeneratedPolicyTest" in request["schema"]["$defs"]
        return {
            "source": "real_laya",
            "model": "qwen3:4b",
            "inference_ms": 0,
            "proposal": {
                "supported": True,
                "operations": [
                    {
                        "type": "upsert_text_rule",
                        "rule": {
                            "id": "letter-a",
                            "operator": "word_contains",
                            "value": "a",
                            "direction": "input",
                        },
                    }
                ],
                "tests": copy.deepcopy(CASES),
            },
        }


@pytest.fixture
def proposal(client, tokens, app):
    fixture = GeneratedFixtureAuthor()
    app.state.policy_authoring.author = fixture
    response = client.post(
        "/api/admin/policies/draft",
        headers=headers(tokens, "security-admin"),
        json={
            "instruction": "Block letter a in model input",
            "base_version": app.state.runtime.snapshot().policy.version,
        },
    )
    assert response.status_code == 200, response.text
    return response.json(), fixture


def preview(client, tokens, proposal, **extra):
    return client.post(
        "/api/admin/policies/preview",
        headers=headers(tokens, "security-admin"),
        json={"proposal_id": proposal["proposal_id"], **extra},
    )


def activate(client, tokens, proposal):
    return client.post(
        "/api/admin/policies/activate",
        headers=headers(tokens, "security-admin"),
        json={
            "proposal_id": proposal["proposal_id"],
            "base_version": proposal["base_version"],
        },
    )


def test_generated_diff_uses_real_controls_without_upstream_or_budget_changes(
    client, tokens, app, project, proposal, monkeypatch
):
    view, fixture = proposal
    assert view["tests"] == CASES
    assert "+++ candidate-policy.yaml" in view["yaml_diff"]

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Pure preview reached upstream, scanner or budget reservation"
        )

    monkeypatch.setattr(app.state.engine.tools, "call", forbidden)
    monkeypatch.setattr(app.state.engine.models, "complete", forbidden)
    monkeypatch.setattr(app.state.engine.scanner, "assess", forbidden)
    monkeypatch.setattr(app.state.engine.ledger, "reserve", forbidden)
    before = app.state.engine.ledger.stats(), app.state.runtime.snapshot()
    response = preview(client, tokens, view, samples=[{"text": "Cat"}])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["tests_passed"] is True
    assert result["comparisons"][0]["before"]["decision"] == "no_local_match"
    assert result["comparisons"][0]["after"]["decision"] == "blocked"
    assert all(item["passed"] for item in result["test_results"])
    assert "authorization" in result["scope"]
    stable = (
        "requests",
        "allowed",
        "blocked",
        "redacted",
        "errors",
        "semantic_calls",
        "audit_retained",
        "audit_dropped",
    )
    after_metrics = app.state.engine.ledger.stats()
    assert {key: after_metrics[key] for key in stable} == {
        key: before[0][key] for key in stable
    }
    assert app.state.runtime.snapshot() is before[1]
    applied = activate(client, tokens, view)
    assert applied.status_code == 200, applied.text
    assert applied.json()["tests_saved"] is True
    suite = SavedRegressionSuite.model_validate(
        yaml.safe_load((project / "config/policy-tests.yaml").read_text())
    )
    assert suite.policy_sha256 == policy_digest(
        app.state.runtime.snapshot().policy
    )
    assert [case.model_dump(mode="json") for case in suite.tests] == CASES
    assert fixture.calls == 1


def test_wrong_expected_outcome_is_not_repaired_and_prevents_activation(
    client, tokens, app, proposal
):
    view, fixture = proposal
    edited = copy.deepcopy(view["tests"])
    edited[0]["expected_decision"] = "no_local_match"
    response = preview(client, tokens, view, tests=edited)
    assert response.status_code == 200
    result = response.json()
    assert result["tests_passed"] is False
    assert (
        result["test_results"][0]["test"]["expected_decision"]
        == "no_local_match"
    )
    assert (
        result["test_results"][0]["comparison"]["after"]["decision"]
        == "blocked"
    )
    assert (
        activate(client, tokens, view).json()["detail"]
        == "proposal_regression_failed"
    )
    assert app.state.runtime.snapshot().policy.version == view["base_version"]
    assert (
        preview(client, tokens, view, tests=CASES).json()["tests_passed"]
        is True
    )
    assert activate(client, tokens, view).status_code == 200
    assert fixture.calls == 1


def test_comparison_pins_one_feed_during_reload_and_requires_repreview(
    client, tokens, app, project, proposal, monkeypatch
):
    from fastfence.modules.control.application.use_cases import policy_preview

    view, _ = proposal
    original = policy_preview.preview_sample
    seen = []

    def inspect(snapshot, *args, **kwargs):
        seen.append(snapshot.feed)
        if len(seen) == 1:
            path = project / "config/signatures.json"
            feed = json.loads(path.read_text())
            feed["version"] += 1
            path.write_text(json.dumps(feed))
            app.state.runtime.policies.reload()
        return original(snapshot, *args, **kwargs)

    monkeypatch.setattr(policy_preview, "preview_sample", inspect)
    response = preview(client, tokens, view)
    assert response.status_code == 200, response.text
    assert all(feed is seen[0] for feed in seen)
    assert response.json()["feed_version"] == seen[0].version
    assert (
        activate(client, tokens, view).json()["detail"]
        == "proposal_feed_changed_preview_again"
    )
    assert (
        preview(client, tokens, view).json()["feed_version"]
        == seen[0].version + 1
    )
    assert activate(client, tokens, view).status_code == 200


def test_file_failure_reports_already_activated_policy_without_false_rollback(
    client, tokens, app, proposal, monkeypatch
):
    view, _ = proposal
    preview(client, tokens, view)

    def cannot_save(*args, **kwargs):
        raise OSError("private filesystem details")

    monkeypatch.setattr(
        "fastfence.app.interfaces.http.authoring_session.save_reviewed_tests",
        cannot_save,
    )
    response = activate(client, tokens, view)
    assert response.status_code == 200
    assert response.json()["warnings"] == ["policy_tests_not_saved"]
    assert response.json()["tests_saved"] is False
    assert "private filesystem" not in response.text
    assert (
        app.state.runtime.snapshot().policy.version == view["base_version"] + 1
    )
    assert activate(client, tokens, view).status_code == 409


@pytest.mark.parametrize(
    "tests", [[], [{**CASES[0], "expected_decision": "allowed"}], CASES + CASES]
)
def test_invalid_or_removed_generated_cases_cannot_mark_proposal_reviewed(
    client, tokens, app, proposal, tests
):
    view, _ = proposal
    response = preview(client, tokens, view, tests=tests)
    assert response.status_code == 422
    assert (
        activate(client, tokens, view).json()["detail"]
        == "proposal_preview_required"
    )
    assert app.state.runtime.snapshot().policy.version == view["base_version"]


def test_stale_base_policy_still_rejects_generated_test_activation(
    client, tokens, app, proposal
):
    view, _ = proposal
    preview(client, tokens, view)
    configure_policy(
        app.state.engine,
        lambda data: data.update(description="Another reviewed policy"),
    )
    assert (
        activate(client, tokens, view).json()["detail"]
        == "policy_base_version_conflict"
    )
