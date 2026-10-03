"""Generated expectations are reviewed data, never an automatically repaired oracle."""

import json

import pytest
import yaml
from pydantic import ValidationError

from fastfence.app.interfaces.http.authoring_regression import (
    SavedRegressionSuite,
    policy_digest,
    save_reviewed_tests,
    yaml_diff,
)
from fastfence.modules.control.application.use_cases.policy_preview import (
    compare_sample,
)
from fastfence.modules.control.domain.models import Snapshot
from fastfence.modules.control.domain.policy_authoring import (
    DraftEnvelope,
    prepare_policy,
)
from fastfence.modules.control.domain.policy_tests import GeneratedPolicyTest
from fastfence.modules.control.persistence.policy import PolicyStore


def operation():
    return {
        "type": "upsert_text_rule",
        "rule": {
            "id": "letter-a",
            "operator": "word_contains",
            "value": "a",
            "direction": "input",
        },
    }


def case_data(**changes):
    data = {"label": "fixture", "text": "Cat", "expected_decision": "blocked"}
    data.update(changes)
    return data


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_decision": "allowed"},
        {"text": "😀" * 1025},
        {"label": " "},
        {"code": "generated executable code"},
        {"target": "all"},
    ],
)
def test_generated_fixture_contract_rejects_invalid_scope_and_execution(
    changes,
):
    with pytest.raises(ValidationError):
        GeneratedPolicyTest.model_validate(case_data(**changes))


def test_envelope_is_backcompatible_bounded_and_has_unique_case_labels():
    assert (
        DraftEnvelope.model_validate(
            {"supported": True, "operations": [operation()]}
        ).tests
        == ()
    )
    for cases in (
        [case_data(), case_data()],
        [case_data(label=str(i)) for i in range(9)],
    ):
        with pytest.raises(ValidationError):
            DraftEnvelope.model_validate(
                {"supported": True, "operations": [operation()], "tests": cases}
            )
    with pytest.raises(ValidationError):
        DraftEnvelope.model_validate(
            {"supported": False, "operations": [], "tests": [case_data()]}
        )


def test_exact_diff_and_saved_suite_replay_against_validated_snapshots(
    configuration, tmp_path
):
    original = PolicyStore(*configuration).snapshot()
    envelope = DraftEnvelope.model_validate(
        {"supported": True, "operations": [operation()], "tests": [case_data()]}
    )
    prepared = prepare_policy(original.policy, envelope)
    candidate = Snapshot(policy=prepared.candidate, feed=original.feed)
    diff = yaml_diff(original.policy, candidate.policy)
    assert diff.startswith("--- base-policy.yaml\n+++ candidate-policy.yaml")
    assert "+    value: a" in diff or "+  value: a" in diff
    suite = SavedRegressionSuite(
        policy_version=candidate.policy.version,
        policy_sha256=policy_digest(candidate.policy),
        feed_version=candidate.feed.version,
        tests=prepared.tests,
    )
    path = tmp_path / "policy-tests.yaml"
    save_reviewed_tests(path, suite)
    replay = SavedRegressionSuite.model_validate(
        yaml.safe_load(path.read_text())
    )
    assert replay == suite
    assert path.stat().st_mode & 0o777 == 0o600
    comparison = compare_sample(original, candidate, replay.tests[0], 0, None)
    assert comparison.before.decision == "no_local_match"
    assert comparison.after.decision == replay.tests[0].expected_decision
    assert comparison.changed
    assert replay.tests[0].expected_decision == "blocked"
    assert "tests" not in json.dumps(candidate.policy.model_dump(mode="json"))


def test_preview_does_not_silently_skip_missing_anonymization_port(
    configuration,
):
    from fastfence.modules.control.application.use_cases.policy_preview import (
        preview_sample,
    )
    from fastfence.modules.control.domain.models import Policy
    from fastfence.modules.control.domain.policy_tests import PolicySample

    original = PolicyStore(*configuration).snapshot()
    data = original.policy.editable()
    data["anonymization"] = {
        "enabled": True,
        "rules": [
            {"id": "fixture", "operator": "literal", "value": "Private project"}
        ],
    }
    snapshot = Snapshot(policy=Policy.model_validate(data), feed=original.feed)
    result = preview_sample(
        snapshot, PolicySample(text="Private project"), 0, None
    )
    assert (
        result.decision == "blocked"
        and result.reason == "anonymization_unavailable"
    )
    result = preview_sample(
        original, PolicySample(text="[FFI1.invalid]"), 0, None
    )
    assert (
        result.decision == "blocked"
        and result.reason == "anonymization_unavailable"
    )
