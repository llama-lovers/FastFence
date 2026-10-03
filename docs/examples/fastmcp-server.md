# Protect a FastMCP server inside a FastAPI application

This complete application connects a real FastMCP `uppercase` tool to FastFence through `ToolsPort`. FastFence's FastAPI application exposes authenticated REST and MCP entry points. Its input controls run **before** the tool, and output controls run before delivery.

The private FastMCP backend is in-process and has no unprotected listening port. This avoids publishing a second route that bypasses the gateway. For a remote MCP backend, replace `Client(backend)` with a client for a fixed trusted URL, supply its separate server-side credential, and restrict direct access to that backend.

## Run

After [installing the package](../getting-started.md), extract the [examples archive](../downloads/fastfence-examples.zip) into `examples/` in your installation directory. Keep `policy.yaml` and `signatures.json` next to `fastmcp_server.py`. Then run:

```sh
python examples/fastmcp_server.py
```

The application listens on `http://127.0.0.1:8010`. It initializes a separate policy and credentials in `state/examples/fastmcp-integration/`; it does not change the main installation. Open this console and connect the `local-agent` and `local-admin` credentials from that directory's `state/credentials.json`.

This standalone example deliberately uses deterministic checks so it runs without a model. The main product policy enables Laya by default. To enable the same semantic input and output checks in this isolated example, follow [Enable Laya](#enable-laya-in-this-example) below.

## Complete server and FastAPI integration

<!-- source: examples/docs/fastmcp_server.py -->

`create_app(..., tools=ProtectedMCPTools())` is the integration point. Register business operations through this port; an ordinary FastAPI route is not automatically protected by FastFence. The public `/integration-info` route returns static metadata only. The verified identity passed to the adapter can also enforce application-specific tenant ownership before execution.

## Policy

<!-- source: examples/docs/policy.yaml -->

## Enable Laya in this example

Stop the example server. From your main installation directory, with Ollama running and the FastFence virtual environment active, prepare the runtime:

```sh
fastfence init --anonymization
export FASTFENCE_AUTHORING_ROOT="$PWD"
```

The environment variable lets the isolated example use the main installation's Laya engine. If you changed the Ollama endpoint, also export the same `FASTFENCE_OLLAMA_URL` in this shell; the example reads environment variables, not the main installation's `.env` file.

Edit `state/examples/fastmcp-integration/config/policy.yaml`, which was created on the example's first start. Preserve its tools, budgets and other controls, increment its current top-level `version`, and replace its `semantic` section with:

```yaml
semantic:
  provider: laya
  model: qwen3:4b
  threshold: 0.7
  timeout_ms: 30000
  scan_output: true
```

Use the assessment model prepared by your main installation if you changed it from Qwen3:4b. Installing Laya alone does not enable assessment: `provider: laya` in this example's own policy is required.

Restart from the same shell:

```sh
python examples/fastmcp_server.py
```

Send `hello` again. For an allowed response, both `semantic_input_status` and `semantic_output_status` should be `passed`. Missing or failed assessment blocks the request. Input denied by an earlier local rule never reaches the assessor or tool.

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
