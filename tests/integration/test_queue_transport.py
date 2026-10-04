import json

import pytest

from fastfence.app.interfaces.http.acp import run_response
from fastfence.app.interfaces.http.openai import verdict_response
from fastfence.modules.control.domain.models import Verdict


def verdict(reason="request_queue_full"):
    return Verdict(
        request_id="0" * 32,
        decision="error",
        reason=reason,
        policy_version=1,
        feed_version=1,
        latency_ms=100,
        queue_wait_ms=75,
        semantic_provider="disabled",
    )


@pytest.mark.parametrize(
    "reason",
    ["request_queue_full", "request_queue_timeout", "request_queue_closed"],
)
def test_openai_queue_error_preserves_protocol_and_wait(reason):
    response = verdict_response(verdict(reason), "model")
    data = json.loads(response.body)
    assert response.status_code == 503
    assert data["error"]["code"] == reason
    assert data["error"]["type"] == "server_error"
    assert data["fastfence"]["queue_wait_ms"] == 75
    assert response.headers["X-FastFence-Queue-Wait-Ms"] == "75"
    assert response.headers.get("Retry-After") == (
        None if reason.endswith("closed") else "1"
    )
    assert data["fastfence"]["upstream_executed"] is False


def test_acp_wait_remains_failed_run_not_success_output():
    response = run_response(verdict(), "agent", "2026-10-04T00:00:00Z")
    data = json.loads(response.body)
    assert response.status_code == 200
    assert data["status"] == "failed" and not data["output"]
    assert data["error"]["data"]["queue_wait_ms"] == 75
    assert response.headers["X-FastFence-Queue-Wait-Ms"] == "75"
