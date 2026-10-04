"""Operators distinguish process liveness from required semantic prerequisites."""

import yaml
from fastapi.testclient import TestClient


def test_liveness_compatibility_and_disabled_semantic_readiness(app, project):
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ready"
        assert health.json()["scope"] == "liveness"
        assert health.json()["readiness_endpoint"] == "/ready"
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["reason"] == "not_required"
        assert ready.headers["cache-control"] == "no-store"
        before = app.state.runtime.ledger.stats()
        policy_path = project / "config/policy.yaml"
        policy = yaml.safe_load(policy_path.read_text())
        policy["version"] += 1
        policy["semantic"].update(provider="laya", model="qwen3:4b")
        policy_path.write_text(yaml.safe_dump(policy))
        app.state.runtime.policies.reload()
        unavailable = client.get("/ready")
        assert unavailable.status_code == 503
        body = unavailable.json()
        assert body["reason"] == "laya_installation_unavailable"
        assert body["scope"] == "required_semantic_prerequisites"
        assert body["inference_tested"] is False
        assert body["business_upstreams_checked"] is False
        assert body["ocr_checked"] is False
        assert str(project) not in unavailable.text
        assert client.get("/health").status_code == 200
        after = app.state.runtime.ledger.stats()
        for key in ("requests", "semantic_calls", "audit_retained"):
            assert after[key] == before[key]
