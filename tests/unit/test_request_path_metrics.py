"""Request-level telemetry remains exact with two semantic stages and audit eviction."""

import pytest

from fastfence.modules.control.domain.models import Verdict
from fastfence.modules.control.persistence.ledger import Ledger


def verdict(input_status="not_run", output_status="not_run", latency=1):
    return Verdict(
        request_id="metric-fixture",
        decision="allowed",
        reason="controls_passed",
        policy_version=1,
        feed_version=1,
        latency_ms=latency,
        semantic_provider="laya",
        semantic_input_status=input_status,
        semantic_output_status=output_status,
    )


@pytest.mark.parametrize(
    "input_status", ["not_run", "passed", "blocked", "error"]
)
@pytest.mark.parametrize(
    "output_status", ["not_run", "passed", "blocked", "error"]
)
def test_two_semantic_stages_count_one_request(input_status, output_status):
    ledger = Ledger(instance_id="request-paths")
    ledger.append(
        "agent", "tenant", "model", verdict(input_status, output_status)
    )
    metrics = ledger.stats()
    semantic = int(input_status != "not_run" or output_status != "not_run")
    assert metrics["requests"] == 1
    assert metrics["semantic_requests"] == semantic
    assert metrics["local_only_requests"] == 1 - semantic


def test_path_counts_survive_eviction_and_exclude_management():
    ledger = Ledger(instance_id="request-paths", audit_limit=1)
    for _ in range(10):
        ledger.append("agent", "tenant", "model", verdict())
        ledger.append("agent", "tenant", "model", verdict("passed", "passed"))
        ledger.record_semantic_call()
        ledger.record_semantic_call()
    ledger.append(
        "admin", "tenant", "policy", verdict(), event_kind="management"
    )
    metrics = ledger.stats()
    assert metrics["requests"] == 20
    assert metrics["semantic_requests"] == metrics["local_only_requests"] == 10
    assert metrics["semantic_calls"] == 20
    assert metrics["audit_retained"] == 1


def test_latency_p95_uses_nearest_rank_at_exact_percentile_boundary():
    ledger = Ledger(instance_id="percentile")
    assert ledger.stats()["p95_latency_ms"] == 0
    for latency in range(1, 21):
        ledger.append("agent", "tenant", "model", verdict(latency=latency))
    metrics = ledger.stats()
    assert metrics["latency_sample_size"] == 20
    assert metrics["p95_latency_ms"] == 19
