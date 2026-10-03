from __future__ import annotations

from tests.conftest import headers


def rpc(client, tokens, method, params, actor="analyst-blue"):
    return client.post(
        "/mcp/",
        headers={**headers(tokens, actor), "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


def test_mcp_protocol_requires_agent_auth_and_masks_all_representations(client, tokens):
    init = {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "fastfence-test", "version": "1"},
    }
    assert (
        client.post(
            "/mcp/",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init},
        ).status_code
        == 401
    )
    assert rpc(client, tokens, "initialize", init, "security-admin").status_code == 401
    assert rpc(client, tokens, "initialize", init).status_code == 200
    response = rpc(
        client,
        tokens,
        "tools/call",
        {"name": "invoke", "arguments": {"tool": "report.contact", "arguments": {}}},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["structuredContent"]["decision"] == "redacted"
    assert "anna@example.org" not in response.text and "sk-demoOnly" not in response.text
    assert "REDACTED" in response.text


def test_mcp_resource_uses_same_tenant_controls(client, tokens):
    good = rpc(client, tokens, "resources/read", {"uri": "memory://blue/forecast"})
    assert "Quarterly forecast" in good.text
    wrong = rpc(client, tokens, "resources/read", {"uri": "memory://green/forecast"})
    assert "Quarterly forecast" not in wrong.text
    assert "error" in wrong.json()


def test_mcp_denied_tool_never_returns_business_result(client, tokens):
    blocked = rpc(
        client,
        tokens,
        "tools/call",
        {
            "name": "invoke",
            "arguments": {
                "tool": "payments.prepare",
                "arguments": {"amount": 100, "recipient": "vendor"},
            },
        },
    )
    result = blocked.json()["result"]["structuredContent"]
    assert result["decision"] == "blocked" and not result["upstream_executed"]
    assert result["output"] is None
