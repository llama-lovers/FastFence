"""Ensure benchmark failures cannot be reported as fast valid requests."""

import pytest

from evaluation.transport_measurements import Proof, Workload, measure


def valid_verdict(identifier: str = "request-1") -> dict:
    return {
        "request_id": identifier,
        "decision": "allowed",
        "reason": "controls_passed",
        "upstream_executed": True,
        "tokens": 20,
        "cost_microusd": 100,
        "policy_version": 1,
        "feed_version": 1,
    }


def allowed_workload() -> Workload:
    return Workload(
        name="allowed",
        query="forecast",
        decision="allowed",
        reason="controls_passed",
    )


def accounted_status() -> dict:
    return {
        "budgets": [
            {
                "subject": "analyst-blue",
                "calls": 1,
                "tokens": 20,
                "cost_microusd": 100,
                "inflight": 0,
            }
        ],
        "metrics": {"requests": 1, "semantic_calls": 0},
    }


def audit_row() -> dict:
    return {"request_id": "request-1", "event_kind": "invocation"}


def test_budget_exhaustion_cannot_masquerade_as_fast_allowed_benchmark():
    verdict = {
        **valid_verdict(),
        "decision": "blocked",
        "reason": "budget_calls",
        "upstream_executed": False,
    }
    with pytest.raises(ValueError, match="Unexpected verdict"):
        Proof().record(verdict, allowed_workload())


def test_duplicate_request_ids_invalidate_evidence():
    proof = Proof()
    proof.record(valid_verdict(), allowed_workload())
    with pytest.raises(ValueError, match="Repeated request"):
        proof.record(valid_verdict(), allowed_workload())


@pytest.mark.parametrize(
    "failure",
    [
        "missing_audit",
        "extra_audit",
        "duplicate_audit",
        "token_mismatch",
        "inflight",
        "semantic",
    ],
)
def test_accounting_and_complete_audit_required(failure):
    proof = Proof()
    proof.record(valid_verdict(), allowed_workload())
    status, audit = accounted_status(), [audit_row()]
    proof.verify(status, audit)
    if failure == "missing_audit":
        audit = []
    elif failure == "extra_audit":
        audit.append({**audit_row(), "request_id": "unexpected"})
    elif failure == "duplicate_audit":
        audit.append(audit_row())
    elif failure == "token_mismatch":
        status["budgets"][0]["tokens"] += 1
    elif failure == "inflight":
        status["budgets"][0]["inflight"] = 1
    elif failure == "semantic":
        status["metrics"]["semantic_calls"] = 1
    with pytest.raises(ValueError):
        proof.verify(status, audit)


async def test_transport_exception_invalidates_measurement_instead_of_being_timed():
    async def broken():
        raise ConnectionError("fixture transport unavailable")

    with pytest.raises(ConnectionError):
        await measure(broken, 10, 8)
