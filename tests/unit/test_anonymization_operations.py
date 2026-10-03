"""Reviewed alias changes preserve unrelated controls and restoration consent."""

import pytest
from pydantic import ValidationError

from fastfence.modules.control.domain.policy_authoring import (
    DraftEnvelope,
    authoring_catalog,
    prepare_policy,
)
from fastfence.modules.control.persistence.policy import PolicyStore


@pytest.fixture
def policy(configuration):
    return PolicyStore(*configuration).snapshot().policy


def envelope(*operations):
    return DraftEnvelope.model_validate(
        {"supported": True, "operations": list(operations)}
    )


def upsert(rule_id="project", **fields):
    return {
        "type": "upsert_anonymization_rule",
        "rule": {
            "id": rule_id,
            "operator": "literal",
            "value": "Private project",
            **fields,
        },
    }


def test_alias_upsert_enables_only_module_and_preserves_privacy_and_blocks(
    policy,
):
    prepared = prepare_policy(policy, envelope(upsert()))
    candidate = prepared.candidate
    assert candidate.anonymization.enabled
    rule = candidate.anonymization.rules[0]
    assert rule.replacement == "ANONIM"
    assert rule.allow_restore is False
    assert rule.direction == "both" and rule.target == "all"
    assert rule.case_sensitive is True
    assert candidate.version == policy.version + 1
    for name in (
        "privacy",
        "budgets",
        "tools",
        "models",
        "semantic",
        "text_rules",
        "signatures_enabled",
    ):
        assert getattr(candidate, name) == getattr(policy, name)
    assert all(
        change.path.startswith("anonymization.") for change in prepared.changes
    )
    catalog = authoring_catalog(candidate)
    assert catalog["anonymization"]["rules"][0]["id"] == "project"
    assert policy.anonymization.rules == ()


def test_exact_id_update_and_removal_preserve_other_rules(policy):
    first = prepare_policy(
        policy, envelope(upsert(), upsert("other", value="Other project"))
    ).candidate
    prepared = prepare_policy(
        first, envelope(upsert(replacement="PROJECT", allow_restore=True))
    )
    assert [rule.id for rule in prepared.candidate.anonymization.rules] == [
        "project",
        "other",
    ]
    assert prepared.candidate.anonymization.rules[0].allow_restore
    assert (
        prepared.candidate.anonymization.rules[1]
        == first.anonymization.rules[1]
    )
    assert (
        prepared.operations[0].model_dump(mode="json")["rule"]["allow_restore"]
        is True
    )
    removed = prepare_policy(
        prepared.candidate,
        envelope({"type": "remove_anonymization_rule", "rule_id": "project"}),
    ).candidate
    assert [rule.id for rule in removed.anonymization.rules] == ["other"]
    assert removed.privacy == first.privacy


def test_unknown_removal_does_not_prepare_or_mutate_policy(policy):
    with pytest.raises(ValueError, match="Unknown anonymization rule"):
        prepare_policy(
            policy,
            envelope(
                {"type": "remove_anonymization_rule", "rule_id": "unknown"}
            ),
        )
    assert policy.anonymization.rules == ()


def test_companion_detector_is_explicit_and_does_not_relax_other_privacy(
    policy,
):
    prepared = prepare_policy(
        policy,
        envelope(
            upsert(
                operator="regex",
                value=r"[a-z]+@[a-z]+\.[a-z]+",
                replacement="EMAIL",
                allow_restore=True,
            ),
            {
                "type": "set_privacy_detector",
                "detector": "pii_email",
                "direction": "both",
                "action": "redact",
            },
        ),
    )
    assert prepared.candidate.privacy.input == policy.privacy.input
    assert (
        prepared.candidate.privacy.action_for("pii_polish_id", "input")
        == "block"
    )
    assert (
        prepared.candidate.privacy.action_for("secret_field", "input")
        == "block"
    )
    assert (
        prepared.candidate.privacy.action_for("pii_email", "input") == "redact"
    )
    assert any(
        change.path.startswith("privacy.detector_actions.pii_email")
        for change in prepared.changes
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"allow_restore": "true"},
        {"replacement": "${private}"},
        {"direction": "unknown"},
        {"operator": "code"},
        {"value": ""},
        {"operator": "regex", "value": "(?=secret)"},
        {"extra": "hidden"},
    ],
)
def test_untrusted_alias_operations_reject_invalid_shapes(fields):
    with pytest.raises(ValidationError):
        envelope(upsert(**fields))


def test_explicit_reversible_mode_does_not_change_rules_or_other_controls(
    policy,
):
    prepared = prepare_policy(
        policy,
        envelope({"type": "set_anonymization_mode", "mode": "reversible"}),
    )
    assert prepared.candidate.anonymization.mode == "reversible"
    assert prepared.candidate.anonymization.rules == policy.anonymization.rules
    assert prepared.candidate.privacy == policy.privacy
    assert [change.path for change in prepared.changes] == [
        "anonymization.mode"
    ]
    with pytest.raises(ValidationError):
        envelope(
            {
                "type": "set_anonymization_mode",
                "mode": "invented",
                "key": "never-author-keys",
            }
        )
