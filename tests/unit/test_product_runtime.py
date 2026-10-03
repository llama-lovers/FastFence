"""Product startup never registers example backends or synthetic tenants."""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from examples.business_tools.credentials import initialize as initialize_example
from fastfence.app.factory import create_app
from fastfence.app.interfaces.cli.bootstrap_config import initialize_config
from fastfence.app.interfaces.cli.initialize import initialize
from fastfence.modules.control.domain.models import Identity
from fastfence.modules.control.persistence.tools import UnconfiguredTools
from fastfence.shared.settings.app_settings import AppSettings


def test_new_credentials_are_local_and_legacy_state_is_preserved(tmp_path):
    local = tmp_path / "local"
    initialize(local)
    tokens = json.loads((local / "credentials.json").read_text())
    assert set(tokens) == {"local-agent", "local-admin"}
    assert not (local / "demo-tokens.json").exists()
    records = json.loads((local / "identities.json").read_text())
    assert {record["identity"]["tenant"] for record in records} == {
        "local",
        "management",
    }
    legacy = tmp_path / "legacy"
    initialize_example(legacy)
    before = {file.name: file.read_bytes() for file in legacy.iterdir()}
    initialize(legacy)
    assert before == {file.name: file.read_bytes() for file in legacy.iterdir()}
    assert not (legacy / "credentials.json").exists()


def test_ambiguous_credential_files_are_not_silently_selected(tmp_path):
    initialize(tmp_path)
    (tmp_path / "demo-tokens.json").write_text("{}")
    with pytest.raises(SystemExit, match="ambiguous"):
        initialize(tmp_path)


def test_default_runtime_rejects_stale_example_allowlists(tmp_path):
    initialize_config(tmp_path)
    initialize(tmp_path / "state")
    policy_path = tmp_path / "config/policy.yaml"
    policy = yaml.safe_load(policy_path.read_text())
    assert policy["tools"] == {}
    policy["tools"] = {
        "knowledge.search": {
            "roles": ["analyst"],
            "timeout_ms": 1000,
            "cost_microusd": 0,
        }
    }
    policy_path.write_text(yaml.safe_dump(policy))
    tokens = json.loads((tmp_path / "state/credentials.json").read_text())
    app = create_app(AppSettings(root=tmp_path))
    with TestClient(app) as client:
        status = client.get(
            "/api/admin/status",
            headers={"Authorization": "Bearer " + tokens["local-admin"]},
        ).json()
        assert status["business_backend"] == "not_configured"
        assert status["tools"] == {
            "connected": [],
            "unavailable": ["knowledge.search"],
        }
        result = client.post(
            "/api/invoke",
            headers={"Authorization": "Bearer " + tokens["local-agent"]},
            json={
                "tool": "knowledge.search",
                "arguments": {"query": "forecast"},
            },
        ).json()
        assert result["decision"] == "blocked"
        assert result["reason"] == "tool_not_implemented"
        assert not result["upstream_executed"] and result["output"] is None


async def test_unconfigured_adapter_cannot_be_called_directly():
    adapter = UnconfiguredTools()
    identity = Identity(
        subject="local-agent", tenant="local", roles=["analyst"]
    )
    assert not adapter.supports("anything")
    with pytest.raises(Exception, match="tool_not_connected"):
        adapter.validate("anything", {}, identity)
    with pytest.raises(Exception, match="tool_not_connected"):
        await adapter.call("anything", {}, identity)


def test_product_source_has_no_simulated_business_handlers():
    source = Path("src/fastfence")
    for path in source.rglob("*.py"):
        text = path.read_text()
        assert "DemoTools" not in text
        assert "SIMULATED" not in text
