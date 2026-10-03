"""Preserved authenticated aliases remain subject to transformed-text rules."""

import pytest

from fastfence.modules.control.application.services.inspection import (
    inspect_payload,
)
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import Policy, Snapshot
from fastfence.modules.control.persistence.policy import PolicyStore


@pytest.mark.parametrize("direction", ["input", "output"])
@pytest.mark.parametrize("privacy_enabled", [False, True])
def test_authenticated_token_is_rechecked_without_new_privacy_findings(
    configuration, direction, privacy_enabled
):
    original = PolicyStore(*configuration).snapshot()
    candidate = original.policy.editable()
    candidate["privacy"]["enabled"] = privacy_enabled
    candidate["text_rules"] = [
        {
            "id": "forbid-recovery-token",
            "operator": "contains",
            "value": "FFR1.",
            "direction": direction,
            "target": "model",
        }
    ]
    snapshot = Snapshot(
        policy=Policy.model_validate(candidate), feed=original.feed
    )
    token = "[FFR1.authenticated-synthetic-callback-fixture]"
    field = "prompt" if direction == "input" else "text"
    # Token cryptography has separate real-code tests. These callbacks model an
    # already verified token whose safe original contains neither PII nor a rule
    # match, and which transform preserves without generating a new alias.
    with pytest.raises(RejectedError) as blocked:
        inspect_payload(
            {field: token},
            snapshot,
            direction,
            target="model",
            reveal=lambda _value: {field: "Private project"},
            anonymize=lambda value: (value, []),
        )
    assert blocked.value.reason == f"{direction}_text_rule"
    assert blocked.value.findings == ["forbid-recovery-token"]
