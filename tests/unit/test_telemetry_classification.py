"""Only trusted call sites classify management events outside invocation metrics."""

import pytest

from fastfence.modules.control.domain.models import Policy, ToolCall, Verdict
from fastfence.modules.control.persistence.ledger import Ledger


@pytest.mark.parametrize("actor", ["analyst-blue", "security-admin"])
@pytest.mark.parametrize("target", ["policy.save", "policy.anything"])
async def test_caller_policy_prefix_cannot_hide_denied_invocations(
    app, tokens, actor, target
):
    runtime = app.state.runtime
    identity = runtime.authenticate(tokens[actor])
    result = await runtime.invoke(identity, ToolCall(tool=target))
    assert result.decision == "blocked" and not result.upstream_executed
    metrics = runtime.ledger.stats()
    assert metrics["requests"] == metrics["blocked"] == 1
    assert metrics["throughput_rps"] > 0
    assert runtime.audit()[0]["event_kind"] == "invocation"


def test_default_audit_classification_ignores_arbitrary_target_text():
    ledger = Ledger(instance_id="telemetry-classification")
    ledger.append(
        "subject",
        "tenant",
        "policy.save",
        Verdict(
            request_id="blocked-invocation",
            decision="blocked",
            reason="target_not_allowlisted",
            policy_version=1,
            feed_version=1,
            latency_ms=1,
            semantic_provider="disabled",
        ),
    )
    assert ledger.stats()["requests"] == ledger.stats()["blocked"] == 1
    assert ledger.audit()[0]["event_kind"] == "invocation"
    ledger.close()


def test_server_policy_management_is_audited_without_invocation_counts(
    app, tokens
):
    runtime = app.state.runtime
    identity = runtime.authenticate(tokens["security-admin"])
    candidate = runtime.snapshot().policy.editable()
    candidate["version"] += 1
    runtime.save_policy(Policy.model_validate(candidate), identity)
    runtime.reload_policy(identity)
    assert runtime.ledger.stats()["requests"] == 0
    assert runtime.ledger.stats()["allowed"] == 0
    records = runtime.audit()
    assert [record["target"] for record in records] == [
        "policy.reload",
        "policy.save",
    ]
    assert all(record["event_kind"] == "management" for record in records)


def test_clients_cannot_choose_management_event_kind(client, tokens):
    response = client.post(
        "/api/invoke",
        headers={"Authorization": "Bearer " + tokens["analyst-blue"]},
        json={"tool": "policy.save", "event_kind": "management"},
    )
    assert response.status_code == 422
