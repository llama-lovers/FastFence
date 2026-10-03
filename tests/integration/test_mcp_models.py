"""MCP model completions use the same policy engine as HTTP completions."""

import pytest

from tests.fixtures.auth import headers


def rpc(client, tokens, method, params, actor="analyst-blue"):
    return client.post(
        "/mcp/",
        headers={
            **headers(tokens, actor),
            "Accept": "application/json, text/event-stream",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


def call(client, tokens, **overrides):
    return rpc(
        client,
        tokens,
        "tools/call",
        {
            "name": "complete",
            "arguments": {
                "model": "qwen3:0.6b",
                "prompt": "Hi",
                "max_output_tokens": 8,
                **overrides,
            },
        },
    )


def install_rule(client, tokens):
    admin = headers(tokens, "security-admin")
    policy = client.get("/api/admin/status", headers=admin).json()["policy"]
    policy["version"] += 1
    policy["text_rules"] = [
        {
            "id": "no-letter-a",
            "operator": "word_contains",
            "value": "a",
            "direction": "both",
            "target": "model",
        }
    ]
    assert (
        client.put("/api/admin/policy", headers=admin, json=policy).status_code
        == 200
    )


def test_mcp_model_tool_discovery_and_management_identity_rejection(
    client, tokens
):
    result = rpc(client, tokens, "tools/list", {}).json()["result"]
    assert "complete" in {tool["name"] for tool in result["tools"]}
    assert (
        rpc(
            client,
            tokens,
            "tools/call",
            {
                "name": "complete",
                "arguments": {"model": "qwen3:0.6b", "prompt": "Hi"},
            },
            "security-admin",
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    ("prompt", "output", "reason", "executed"),
    [
        ("Cat", "Hi", "input_text_rule", False),
        ("Hi", "Cat", "output_text_rule", True),
        ("Hi", "Hello", "controls_passed", True),
    ],
)
def test_mcp_model_calls_enforce_authored_rules_and_audit(
    client, tokens, app, monkeypatch, prompt, output, reason, executed
):
    install_rule(client, tokens)
    seen = []

    async def complete(*args, **kwargs):
        seen.append(args)
        return {"text": output, "model": "qwen3:0.6b"}, 5

    monkeypatch.setattr(app.state.engine.models, "complete", complete)
    response = call(client, tokens, prompt=prompt)
    assert response.status_code == 200
    verdict = response.json()["result"]["structuredContent"]
    assert verdict["reason"] == reason
    assert verdict["upstream_executed"] is executed
    assert bool(seen) is executed
    assert (verdict["output"] is None) is (reason != "controls_passed")
    if reason != "controls_passed":
        assert verdict["decision"] == "blocked"
        assert '"text": "Cat"' not in response.text
    audit = app.state.engine.ledger.audit()
    assert any(row["request_id"] == verdict["request_id"] for row in audit)


@pytest.mark.parametrize(
    "overrides",
    [{"max_output_tokens": 0}, {"max_output_tokens": 2049}, {"model": ""}],
)
def test_mcp_invalid_model_request_never_executes(
    client, tokens, app, monkeypatch, overrides
):
    async def forbidden(*args, **kwargs):
        pytest.fail("Invalid MCP request executed a model")

    monkeypatch.setattr(app.state.engine.models, "complete", forbidden)
    result = call(client, tokens, **overrides).json()
    assert result.get("error") or result["result"].get("isError")
    assert app.state.engine.ledger.stats()["requests"] == 0
