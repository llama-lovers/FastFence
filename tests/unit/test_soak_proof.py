"""Invalidate soak evidence on cross-generation decisions or bounded-audit drift."""

import copy

import pytest

from evaluation.soak_proof import Generation, SoakProof


def verdict(identifier="one", policy=1, feed=2, **change):
    return {
        "request_id": identifier,
        "policy_version": policy,
        "feed_version": feed,
        "decision": "allowed",
        "reason": "controls_passed",
        "upstream_executed": True,
        "tokens": 20,
        "cost_microusd": 100,
        **change,
    }


def proof_fixture():
    proof = SoakProof()
    proof.register(
        Generation(
            policy_version=1,
            feed_version=2,
            input_action="block",
            dynamic_signature=False,
        )
    )
    names = [
        "allowed",
        "signature",
        "sensitive_input",
        "output_redaction",
        "rbac",
        "dynamic_signature",
    ]
    for case in names:
        for protocol in ["http", "mcp"]:
            decision, reason, executed = proof.generations[(1, 2)].expected(
                case
            )
            proof.record(
                verdict(
                    f"{case}-{protocol}",
                    decision=decision,
                    reason=reason,
                    upstream_executed=executed,
                    tokens=20 if executed else 0,
                    cost_microusd=100 if executed else 0,
                ),
                case,
                protocol,
            )
    metrics = {
        "requests": 12,
        "semantic_calls": 0,
        "errors": 0,
        **proof.decisions,
        "audit_retained": 1,
        "audit_dropped": 11,
        "latency_sample_size": 12,
    }
    status = {
        "metrics": metrics,
        "budgets": [
            {
                "subject": "analyst-blue",
                "calls": proof.calls,
                "tokens": proof.tokens,
                "cost_microusd": proof.cost,
                "inflight": 0,
            }
        ],
    }
    audit = [
        {
            "request_id": "dynamic_signature-mcp",
            "sequence": 12,
            "policy_version": 1,
            "feed_version": 2,
            "decision": "allowed",
            "reason": "controls_passed",
            "upstream_executed": True,
        }
    ]
    return proof, status, audit


def test_retention_tail_and_eviction_counts_match_bounded_ring():
    proof, status, audit = proof_fixture()
    proof.verify(status, audit, 1)


@pytest.mark.parametrize(
    "change",
    [
        {"policy_version": 2},
        {"upstream_executed": 1},
        {"feed_version": 3},
        {
            "decision": "blocked",
            "reason": "budget_calls",
            "upstream_executed": False,
        },
        {"output": "anna@example.org"},
    ],
)
def test_unknown_mixed_versions_budget_denial_and_sensitive_output_invalidate(
    change,
):
    proof, _, _ = proof_fixture()
    with pytest.raises(ValueError):
        proof.record(verdict("new", **change), "allowed", "http")


def test_same_payload_decision_is_checked_against_its_own_snapshot():
    proof = SoakProof()
    proof.register(
        Generation(
            policy_version=1,
            feed_version=2,
            input_action="block",
            dynamic_signature=True,
        )
    )
    proof.register(
        Generation(
            policy_version=2,
            feed_version=3,
            input_action="redact",
            dynamic_signature=False,
        )
    )
    proof.record(
        verdict(
            "old",
            decision="blocked",
            reason="attack_signature",
            upstream_executed=False,
            tokens=0,
            cost_microusd=0,
        ),
        "dynamic_signature",
        "http",
    )
    proof.record(verdict("new", policy=2, feed=3), "dynamic_signature", "mcp")
    with pytest.raises(ValueError, match="Unexpected"):
        proof.record(verdict("mixed-outcome"), "dynamic_signature", "http")


@pytest.mark.parametrize(
    "target,key,value",
    [
        ("metrics", "audit_dropped", 0),
        ("metrics", "latency_sample_size", 3),
        ("metrics", "allowed", 1),
        ("metrics", "semantic_calls", 1),
        ("budget", "tokens", 41),
        ("budget", "inflight", 1),
        ("audit", "sequence", 1),
        ("audit", "feed_version", 3),
        ("audit", "output", "private payload"),
    ],
)
def test_accounting_metrics_or_retained_audit_drift_invalidates(
    target, key, value
):
    proof, status, audit = proof_fixture()
    item = (
        status["metrics"]
        if target == "metrics"
        else status["budgets"][0]
        if target == "budget"
        else audit[0]
    )
    item[key] = value
    with pytest.raises(ValueError):
        proof.verify(status, audit, 1)


def test_published_but_unexercised_generation_cannot_be_claimed_validated():
    proof, status, audit = proof_fixture()
    proof.register(
        Generation(
            policy_version=2,
            feed_version=3,
            input_action="redact",
            dynamic_signature=True,
        )
    )
    with pytest.raises(ValueError, match="not exercised"):
        proof.verify(status, audit, 1)


def test_duplicate_return_or_audit_entries_invalidate():
    proof, status, audit = proof_fixture()
    with pytest.raises(ValueError, match="Duplicate"):
        proof.record(verdict("allowed-http"), "allowed", "http")
    with pytest.raises(ValueError):
        proof.verify(status, [*audit, copy.deepcopy(audit[0])], 1)


def test_missing_workload_in_one_protocol_of_one_generation_invalidates():
    proof, status, audit = proof_fixture()
    proof.coverage.remove((1, 2, "sensitive_input", "mcp"))
    with pytest.raises(ValueError, match="every workload"):
        proof.verify(status, audit, 1)
