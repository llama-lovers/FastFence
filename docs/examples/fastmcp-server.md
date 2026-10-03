# Protect a FastMCP server inside a FastAPI application

This complete application connects a real FastMCP `uppercase` tool to FastFence through `ToolsPort`. FastFence's FastAPI application exposes authenticated REST and MCP entry points. Its input controls run **before** the tool, and output controls run before delivery.

The private FastMCP backend is in-process and has no unprotected listening port. This avoids publishing a second route that bypasses the gateway. For a remote MCP backend, replace `Client(backend)` with a client for a fixed trusted URL, supply its separate server-side credential, and restrict direct access to that backend.

## Run

From the repository, after `uv sync --locked`:

```sh
uv run python -m examples.docs.fastmcp_server
```

The application listens on `http://127.0.0.1:8010`. It initializes a separate policy and credentials in `state/examples/fastmcp-integration/`; it does not change the main installation. Open this console and connect the `local-agent` and `local-admin` credentials from that directory's `state/credentials.json`.

The example uses deterministic checks so it runs without a model. This is an explicit example profile; the product's default policy enables Laya. To add semantic checking here, set up Laya for this installation and configure its trusted `authoring_root` as described in [installation](../getting-started.md).

## Complete server and FastAPI integration

<!-- source: examples/docs/fastmcp_server.py -->

`create_app(..., tools=ProtectedMCPTools())` is the integration point. Register business operations through this port; an ordinary FastAPI route is not automatically protected by FastFence. The public `/integration-info` route returns static metadata only. The verified identity passed to the adapter can also enforce application-specific tenant ownership before execution.

## Policy

<!-- source: examples/docs/policy.yaml -->

## Invoke through REST

Set `FASTFENCE_AGENT_TOKEN` to the example's provisioned agent token in your shell, then:

```sh
curl http://127.0.0.1:8010/api/invoke \
  -H "Authorization: Bearer $FASTFENCE_AGENT_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"tool":"text.uppercase","arguments":{"text":"hello"}}'
```

Expected: `decision: allowed`, `upstream_executed: true`, and `output.text: HELLO`.

Repeat with `{"text":"forbidden"}`. Expected: `decision: blocked`, `upstream_executed: false`. FastFence blocks the exact sample word before calling FastMCP. The same controls apply through the [FastMCP client](mcp-client.md), using this server's port and tool identifier.

For an output-only test, add a rule matching `HELLO`, direction `output`, target `tool`, case sensitive. The tool executes, but its response is withheld. Inspect **Activity** to distinguish input and output blocks. HTTP 200 by itself never means the operation was allowed.
