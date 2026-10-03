import json

import yaml
from fastapi.testclient import TestClient

from examples.docs.fastmcp_server import build_example


def test_real_fastmcp_backend_is_protected_on_input_and_output(tmp_path):
    app = build_example(tmp_path)
    credentials = json.loads((tmp_path / "state/credentials.json").read_text())
    agent = {"Authorization": "Bearer " + credentials["local-agent"]}
    admin = {"Authorization": "Bearer " + credentials["local-admin"]}
    with TestClient(app) as client:
        body = {"tool": "text.uppercase", "arguments": {"text": "hello"}}
        assert client.post("/api/invoke", json=body).status_code == 401
        allowed = client.post("/api/invoke", json=body, headers=agent).json()
        assert allowed["decision"] == "allowed"
        assert allowed["output"] == {"text": "HELLO"}
        assert allowed["upstream_executed"] is True
        body["arguments"]["text"] = "forbidden"
        blocked = client.post("/api/invoke", json=body, headers=agent).json()
        assert blocked["decision"] == "blocked"
        assert blocked["upstream_executed"] is False
        policy = yaml.safe_load((tmp_path / "config/policy.yaml").read_text())
        policy["version"] += 1
        policy["text_rules"].append(
            {
                "id": "output",
                "operator": "contains",
                "value": "HELLO",
                "direction": "output",
                "target": "tool",
                "case_sensitive": True,
            }
        )
        assert (
            client.put(
                "/api/admin/policy", headers=admin, json=policy
            ).status_code
            == 200
        )
        body["arguments"]["text"] = "hello"
        denied = client.post("/api/invoke", json=body, headers=agent).json()
        assert denied["decision"] == "blocked"
        assert denied["upstream_executed"] is True
        assert denied["output"] is None


def test_example_restart_preserves_operator_edits_and_credentials(tmp_path):
    app = build_example(tmp_path)
    credentials = (tmp_path / "state/credentials.json").read_bytes()
    path = tmp_path / "config/policy.yaml"
    policy = yaml.safe_load(path.read_text())
    policy["description"] = "My integration"
    path.write_text(yaml.safe_dump(policy))
    with TestClient(app):
        pass
    restarted = build_example(tmp_path)
    with TestClient(restarted):
        assert (
            restarted.state.runtime.snapshot().policy.description
            == "My integration"
        )
    assert (tmp_path / "state/credentials.json").read_bytes() == credentials
