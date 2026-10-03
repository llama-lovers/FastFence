import pytest
from pydantic import ValidationError

from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.policy_authoring import (
    DraftEnvelope,
    prepare_policy,
)
from fastfence.modules.control.domain.privacy import Privacy


def proposal(*operations):
    return DraftEnvelope.model_validate(
        {"supported": True, "operations": list(operations)}
    )


@pytest.fixture
def policy(configuration):
    from fastfence.modules.control.persistence.policy import PolicyStore

    return PolicyStore(*configuration).snapshot().policy


def test_selective_email_override_preserves_every_other_control(policy):
    operation = {
        "type": "set_privacy_detector",
        "detector": "pii_email",
        "direction": "input",
        "action": "redact",
    }
    prepared = prepare_policy(policy, proposal(operation))
    candidate = prepared.candidate
    assert candidate.version == policy.version + 1
    assert candidate.privacy.action_for("pii_email", "input") == "redact"
    assert candidate.privacy.action_for("pii_polish_id", "input") == "block"
    assert candidate.privacy.action_for("secret_field", "input") == "block"
    assert candidate.privacy.action_for("pii_email", "output") == "redact"
    for field in ("budgets", "tools", "models", "semantic", "text_rules"):
        assert getattr(candidate, field) == getattr(policy, field)
    assert [change.path for change in prepared.changes] == [
        "privacy.detector_actions.pii_email"
    ]
    with pytest.raises(TypeError):
        prepared.changes[0].after["input"] = "block"
    assert prepared.changes[0].model_dump()["after"]["input"] == "redact"


def test_broad_privacy_operation_clears_only_affected_overrides(policy):
    data = policy.editable()
    data["privacy"]["detector_actions"] = {
        "pii_email": {"input": "redact", "output": "block"}
    }
    modified = Policy.model_validate(data)
    prepared = prepare_policy(
        modified,
        proposal(
            {"type": "set_privacy", "direction": "input", "action": "block"}
        ),
    )
    assert (
        prepared.candidate.privacy.action_for("pii_email", "input") == "block"
    )
    assert (
        prepared.candidate.privacy.action_for("pii_email", "output") == "block"
    )


def test_disabled_privacy_is_never_enabled_without_preview_warning(policy):
    data = policy.editable()
    data["privacy"]["enabled"] = False
    prepared = prepare_policy(
        Policy.model_validate(data),
        proposal(
            {
                "type": "set_privacy_detector",
                "detector": "pii_email",
                "direction": "output",
                "action": "block",
            }
        ),
    )
    assert prepared.candidate.privacy.enabled
    assert prepared.warnings == (
        "privacy_was_disabled_enabling_existing_detectors",
    )


@pytest.mark.parametrize(
    "tool,roles",
    [
        ("invented.tool", ["analyst"]),
        ("payments.prepare", ["analyst"]),
        ("knowledge.search", ["admin"]),
        ("knowledge.search", ["operator", "operator"]),
    ],
)
def test_unknown_or_widening_tool_operations_are_rejected(policy, tool, roles):
    with pytest.raises(ValueError):
        prepare_policy(
            policy,
            proposal(
                {"type": "restrict_tool_roles", "tool": tool, "roles": roles}
            ),
        )


def test_role_restriction_preserves_tool_limits_and_unrelated_controls(policy):
    prepared = prepare_policy(
        policy,
        proposal(
            {
                "type": "restrict_tool_roles",
                "tool": "knowledge.search",
                "roles": ["operator"],
            }
        ),
    )
    candidate = prepared.candidate
    assert candidate.tools["knowledge.search"].roles == ("operator",)
    assert (
        candidate.tools["knowledge.search"].timeout_ms
        == policy.tools["knowledge.search"].timeout_ms
    )
    assert (
        candidate.tools["knowledge.search"].cost_microusd
        == policy.tools["knowledge.search"].cost_microusd
    )
    assert (
        candidate.privacy == policy.privacy
        and candidate.budgets == policy.budgets
    )


@pytest.mark.parametrize(
    "operation",
    [
        {
            "type": "set_privacy_detector",
            "detector": "invented",
            "direction": "both",
            "action": "redact",
        },
        {"type": "set_privacy", "direction": "both", "action": "allow"},
        {
            "type": "restrict_tool_roles",
            "tool": "knowledge.search",
            "roles": [],
        },
        {"type": "generated_code", "code": "print('no')"},
    ],
)
def test_unsupported_operation_contract_rejects_arbitrary_shapes(operation):
    with pytest.raises(ValidationError):
        proposal(operation)


def test_selective_policy_config_is_deeply_immutable_and_roundtrips():
    privacy = Privacy.model_validate(
        {"detector_actions": {"pii_email": {"input": "redact"}}}
    )
    with pytest.raises(TypeError):
        privacy.detector_actions["pii_email"] = None
    with pytest.raises(ValidationError):
        privacy.detector_actions["pii_email"].input = "block"
    assert Privacy.model_validate_json(privacy.model_dump_json()) == privacy
    with pytest.raises(ValidationError):
        Privacy.model_validate(
            {"detector_actions": {"passwords": {"input": "redact"}}}
        )


def test_noop_and_oversized_operation_batches_are_rejected(policy):
    with pytest.raises(ValueError, match="does not change"):
        prepare_policy(
            policy,
            proposal(
                {"type": "set_privacy", "direction": "input", "action": "block"}
            ),
        )
    with pytest.raises(ValidationError):
        proposal(
            *[{"type": "set_privacy", "direction": "input", "action": "redact"}]
            * 9
        )


def test_upsert_rule_replaces_only_reviewed_identifier(policy):
    first = {
        "type": "upsert_text_rule",
        "rule": {"id": "letter", "operator": "word_contains", "value": "a"},
    }
    prepared = prepare_policy(policy, proposal(first))
    second = {
        "type": "upsert_text_rule",
        "rule": {"id": "letter", "operator": "word_contains", "value": "b"},
    }
    changed = prepare_policy(prepared.candidate, proposal(second))
    assert len(changed.candidate.text_rules) == 1
    assert changed.candidate.text_rules[0].value == "b"
    assert changed.candidate.models == policy.models
