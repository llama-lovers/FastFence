"""Independent acceptance checks derived from Goldman's control-layer requirements."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from fastfence.modules.control.application.services.engine import Engine
from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import Identity, ToolCall
from fastfence.modules.control.persistence.config_providers import (
    ConfigSourceError,
)
from fastfence.modules.control.persistence.ledger import Ledger
from fastfence.modules.control.persistence.models import (
    OllamaModels,
    SemanticScanner,
)
from fastfence.modules.control.persistence.policy import PolicyStore
from fastfence.modules.control.persistence.tools import DemoTools

ROOT = Path(__file__).resolve().parents[2]


class RecordingTools(DemoTools):
    def __init__(self):
        self.executions = []
        self.fixed_output = None

    async def call(self, tool, arguments, identity):
        self.executions.append((tool, arguments, identity.subject))
        if self.fixed_output is not None:
            return self.fixed_output
        return await super().call(tool, arguments, identity)


@pytest.fixture
def boundary(tmp_path):
    policy_file = tmp_path / "policy.yaml"
    feed_file = tmp_path / "signatures.json"
    policy_file.write_text((ROOT / "config/policy.offline.yaml").read_text())
    feed_file.write_text((ROOT / "config/signatures.json").read_text())
    tools = RecordingTools()
    store = PolicyStore(policy_file, feed_file)
    ledger = Ledger(instance_id="acceptance")
    engine = Engine(
        policies=store,
        ledger=ledger,
        tools=tools,
        scanner=SemanticScanner("http://127.0.0.1:1", "http://127.0.0.1:1"),
        models=OllamaModels("http://127.0.0.1:1"),
    )
    identity = Identity(
        subject="acceptance-analyst", tenant="alpha", roles=["analyst"]
    )
    yield engine, tools, ledger, identity, policy_file
    ledger.close()


def update_policy(engine, path, mutate):
    candidate = yaml.safe_load(path.read_text())
    candidate["version"] += 1
    mutate(candidate)
    path.write_text(yaml.safe_dump(candidate))
    engine.policies.reload()


@pytest.mark.parametrize(
    ("tool", "arguments", "reason"),
    [
        (
            "shell.execute",
            {"command": "echo harmless"},
            "target_not_allowlisted",
        ),
        (
            "payments.prepare",
            {"amount": 100, "recipient": "approved"},
            "role_not_allowed",
        ),
        ("memory.read", {"resource": "beta/private"}, "cross_tenant_resource"),
        (
            "knowledge.search",
            {"query": "pickle.loads(payload)"},
            "attack_signature",
        ),
        (
            "knowledge.search",
            {"query": "api_key=opaquePrivateToken123"},
            "input_sensitive_data",
        ),
    ],
)
async def test_denial_never_reaches_business_tool(
    boundary, tool, arguments, reason
):
    engine, tools, ledger, identity, _ = boundary
    result = await engine.invoke(
        identity, ToolCall(tool=tool, arguments=arguments)
    )
    assert result.decision == "blocked"
    assert result.reason == reason
    assert not result.upstream_executed
    assert tools.executions == []
    assert ledger.audit()[0]["reason"] == reason


async def test_authorized_work_is_allowed(boundary):
    engine, tools, _, identity, _ = boundary
    result = await engine.invoke(
        identity,
        ToolCall(
            tool="knowledge.search", arguments={"query": "quarterly forecast"}
        ),
    )
    assert result.decision == "allowed"
    assert len(tools.executions) == 1
    assert "quarterly forecast" in result.output["answer"]


async def test_sensitive_nested_output_and_audit_do_not_leak(boundary):
    engine, tools, ledger, identity, _ = boundary
    tools.fixed_output = {
        "nested": {
            "api_key": "opaqueSecretWithNoVendorPrefix",
            "password": "notPublic123!",
        },
        "people": [{"email": "person@example.org", "national_id": 12345678901}],
        "public": "Quarterly report is ready.",
    }
    result = await engine.invoke(
        identity,
        ToolCall(
            tool="knowledge.search", arguments={"query": "quarterly report"}
        ),
    )
    rendered = json.dumps(result.model_dump())
    assert result.decision == "redacted"
    for secret in [
        "opaqueSecretWithNoVendorPrefix",
        "notPublic123!",
        "person@example.org",
        "12345678901",
    ]:
        assert secret not in rendered
        assert secret not in json.dumps(ledger.audit())
    assert result.output["public"] == "Quarterly report is ready."


async def test_parallel_requests_cannot_exceed_call_limit(boundary):
    engine, tools, ledger, identity, path = boundary
    update_policy(
        engine, path, lambda p: p["budgets"]["analyst"].update(calls=3)
    )
    results = await asyncio.gather(
        *[
            engine.invoke(
                identity,
                ToolCall(
                    tool="knowledge.search", arguments={"query": f"report {i}"}
                ),
            )
            for i in range(16)
        ]
    )
    assert sum(r.decision == "allowed" for r in results) == 3
    assert len(tools.executions) == 3
    assert ledger.budgets()[0]["calls"] == 3
    assert ledger.budgets()[0]["inflight"] == 0


async def test_model_failure_does_not_execute_tool(boundary):
    engine, tools, _, identity, path = boundary

    class BrokenScanner:
        async def assess(self, text, config):
            raise ModelUnavailableError("provider unavailable")

    update_policy(
        engine, path, lambda p: p["semantic"].update(provider="ollama")
    )
    engine.scanner = BrokenScanner()
    result = await engine.invoke(
        identity,
        ToolCall(
            tool="knowledge.search", arguments={"query": "quarterly report"}
        ),
    )
    assert result.decision in {"error", "blocked"}
    assert result.reason == "model_unavailable_fail_closed"
    assert not result.upstream_executed
    assert tools.executions == []


async def test_invalid_reload_keeps_last_good_policy(boundary):
    engine, tools, _, identity, path = boundary
    original_version = engine.policies.snapshot().policy.version
    path.write_text("version: 999\ntools: unvalidated\n")
    with pytest.raises(ConfigSourceError):
        engine.policies.reload()
    result = await engine.invoke(
        identity,
        ToolCall(
            tool="knowledge.search", arguments={"query": "quarterly report"}
        ),
    )
    assert result.decision == "allowed"
    assert result.policy_version == original_version
    assert len(tools.executions) == 1


async def test_updated_policy_changes_actual_enforcement(boundary):
    engine, tools, _, identity, path = boundary
    call = ToolCall(
        tool="knowledge.search", arguments={"query": "quarterly report"}
    )
    before = await engine.invoke(identity, call)
    update_policy(
        engine,
        path,
        lambda p: p["tools"]["knowledge.search"].update(roles=["operator"]),
    )
    after = await engine.invoke(identity, call)
    assert before.decision == "allowed"
    assert after.decision == "blocked"
    assert after.reason == "role_not_allowed"
    assert after.policy_version > before.policy_version
    assert len(tools.executions) == 1
