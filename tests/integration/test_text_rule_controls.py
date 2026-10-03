"""User-authored restrictions govern content rather than JSON transport metadata."""

from __future__ import annotations

import json

import pytest
import yaml

from tests.fixtures.auth import headers


def rule(**overrides):
    return {
        "id": "no-letter-a",
        "operator": "word_contains",
        "value": "a",
        "direction": "output",
        "target": "model",
        "action": "block",
        "case_sensitive": False,
        **overrides,
    }


def install(client, tokens, *rules):
    admin = headers(tokens, "security-admin")
    policy = client.get("/api/admin/status", headers=admin).json()["policy"]
    policy["version"] += 1
    policy["text_rules"] = list(rules)
    response = client.put("/api/admin/policy", headers=admin, json=policy)
    assert response.status_code == 200, response.text
    return policy


def complete(client, tokens, **overrides):
    return client.post(
        "/api/models/complete",
        headers=headers(tokens),
        json={"model": "qwen3:0.6b", "prompt": "tiny report", **overrides},
    )


@pytest.mark.parametrize(
    ("text", "decision"),
    [("tiny report", "allowed"), ("DATA", "blocked"), ("dątą", "allowed")],
)
def test_output_word_rule_excludes_prompt_and_transport_metadata(
    client, tokens, app, monkeypatch, text, decision
):
    install(client, tokens, rule())
    calls = []

    async def upstream(*args, **kwargs):
        calls.append(args)
        return {"text": text, "model": "metadata", "finish_reason": "stop"}, 5

    monkeypatch.setattr(app.state.engine.models, "complete", upstream)
    response = complete(client, tokens, prompt="Please answer carefully").json()
    assert response["decision"] == decision
    assert response["upstream_executed"] and len(calls) == 1
    assert (response["output"] is None) == (decision == "blocked")
    if decision == "blocked":
        assert response["reason"] == "output_text_rule"
        assert response["findings"] == ["no-letter-a"]
        assert text not in json.dumps(app.state.engine.ledger.audit())


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "data"},
        {"prompt": "", "messages": [{"role": "user", "content": "DATA"}]},
        {"prompt": "tiny report", "stop": ["alpha"]},
    ],
)
def test_input_rule_covers_actual_prompt_messages_and_stops_before_upstream(
    client, tokens, app, monkeypatch, payload
):
    install(client, tokens, rule(direction="input"))
    calls = []

    async def upstream(*args, **kwargs):
        calls.append(args)
        return {"text": "tiny report"}, 5

    monkeypatch.setattr(app.state.engine.models, "complete", upstream)
    response = complete(client, tokens, **payload).json()
    assert response["decision"] == "blocked"
    assert response["reason"] == "input_text_rule"
    assert not response["upstream_executed"] and calls == []
    assert response["output"] is None and response["findings"]
    assert app.state.engine.ledger.budgets() == []


def test_message_role_and_structural_fields_are_not_text_rule_content(
    client, tokens, app, monkeypatch
):
    policy = install(client, tokens, rule(direction="input"))
    policy["version"] += 1
    policy["models"]["alpha"] = policy["models"]["qwen3:0.6b"]
    assert (
        client.put(
            "/api/admin/policy",
            headers=headers(tokens, "security-admin"),
            json=policy,
        ).status_code
        == 200
    )
    calls = []

    async def upstream(model, prompt, maximum, timeout, **options):
        calls.append(options["messages"])
        return {"text": "data"}, 5

    monkeypatch.setattr(app.state.engine.models, "complete", upstream)
    response = complete(
        client,
        tokens,
        model="alpha",
        prompt="",
        messages=[{"role": "assistant", "content": "tiny report"}],
    ).json()
    assert response["decision"] == "allowed"
    assert calls[0][0].role == "assistant"


def test_tool_rules_inspect_values_but_exclude_argument_keys_and_tool_name(
    client, tokens
):
    install(client, tokens, rule(direction="input", target="tool"))
    common = {"tool": "payments.prepare", "arguments": {"amount": 7}}
    allowed = client.post(
        "/api/invoke",
        headers=headers(tokens, "operator-blue"),
        json={**common, "arguments": {"amount": 7, "recipient": "vendor"}},
    ).json()
    assert allowed["decision"] == "allowed" and allowed["upstream_executed"]
    denied = client.post(
        "/api/invoke",
        headers=headers(tokens, "operator-blue"),
        json={**common, "arguments": {"amount": 7, "recipient": "alpha"}},
    ).json()
    assert denied["decision"] == "blocked" and not denied["upstream_executed"]


@pytest.mark.parametrize("target", ["model", "tool", "all"])
def test_target_scope_is_explicit_for_model_and_tool_output(
    client, tokens, app, monkeypatch, target
):
    install(client, tokens, rule(target=target))

    async def upstream(*args, **kwargs):
        return {"text": "data"}, 5

    monkeypatch.setattr(app.state.engine.models, "complete", upstream)
    model_result = complete(client, tokens).json()
    tool_result = client.post(
        "/api/invoke",
        headers=headers(tokens),
        json={"tool": "knowledge.search", "arguments": {"query": "tiny"}},
    ).json()
    assert model_result["decision"] == (
        "blocked" if target in {"model", "all"} else "allowed"
    )
    assert tool_result["decision"] == (
        "blocked" if target in {"tool", "all"} else "allowed"
    )


@pytest.mark.parametrize(
    "rules",
    [
        [rule(operator="eval")],
        [rule(), rule()],
        [rule(value=" ")],
        [rule(value="a-b")],
        [rule(value="a" * 129)],
        [rule(python="arbitrary_code")],
        [rule(id=f"rule-{index}") for index in range(65)],
    ],
)
def test_invalid_rules_cannot_replace_active_policy(client, tokens, rules):
    admin = headers(tokens, "security-admin")
    original = client.get("/api/admin/status", headers=admin).json()["policy"]
    candidate = {
        **original,
        "version": original["version"] + 1,
        "text_rules": rules,
    }
    rejected = client.put("/api/admin/policy", headers=admin, json=candidate)
    assert rejected.status_code == 422
    assert (
        client.get("/api/admin/status", headers=admin).json()["policy"]
        == original
    )


def test_rule_reload_changes_future_calls_and_malformed_update_keeps_last_good(
    client, tokens, app, project, monkeypatch
):
    calls = []

    async def upstream(*args, **kwargs):
        calls.append(args)
        return {"text": "data"}, 5

    monkeypatch.setattr(app.state.engine.models, "complete", upstream)
    assert complete(client, tokens).json()["decision"] == "allowed"
    snapshot = app.state.engine.policies.snapshot()
    candidate = snapshot.policy.editable()
    candidate["version"] += 1
    candidate["text_rules"] = [rule()]
    path = project / "config/policy.yaml"
    path.write_text(yaml.safe_dump(candidate))
    admin = headers(tokens, "security-admin")
    assert client.post("/api/admin/reload", headers=admin).status_code == 200
    assert complete(client, tokens).json()["decision"] == "blocked"
    assert snapshot.policy.version != candidate["version"]
    candidate["version"] += 1
    candidate["text_rules"][0]["operator"] = "eval"
    path.write_text(yaml.safe_dump(candidate))
    assert client.post("/api/admin/reload", headers=admin).status_code == 409
    active = app.state.engine.policies.snapshot()
    assert active.policy.version == candidate["version"] - 1
    assert complete(client, tokens).json()["decision"] == "blocked"
    assert len(calls) == 3


def test_both_direction_rules_block_before_or_after_execution_as_appropriate(
    client, tokens, app, monkeypatch
):
    install(client, tokens, rule(direction="both"))
    calls = []

    async def upstream(*args, **kwargs):
        calls.append(args)
        return {"text": "data"}, 5

    monkeypatch.setattr(app.state.engine.models, "complete", upstream)
    incoming = complete(client, tokens, prompt="data").json()
    outgoing = complete(client, tokens, prompt="tiny report").json()
    assert incoming["reason"] == "input_text_rule"
    assert not incoming["upstream_executed"]
    assert outgoing["reason"] == "output_text_rule"
    assert outgoing["upstream_executed"]
    assert len(calls) == 1
