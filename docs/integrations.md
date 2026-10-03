# Integrations

FastFence protects operations routed through its gateway. Existing agent connectors need explicit routing through the protected adapters; installing FastFence does not automatically intercept an agent's other network traffic.

## REST tools and models

Agent routes require a provisioned agent bearer credential. Management routes require a separate management credential. The interactive local API schema is available at `http://127.0.0.1:8000/docs`.

Protected REST writes authenticate before consuming or parsing their body. Invocation envelopes are limited to **512 KiB** of actual streamed bytes, including chunked requests and JSON escaping. Management envelopes use the larger of 512 KiB and the trusted `FASTFENCE_MAX_CONFIG_SOURCE_BYTES` setting (at most 2 MiB). Oversized bodies receive a sanitized `413`; these transport denials do not execute upstream calls or reserve budgets. The active policy still independently bounds the logical input payload to at most 64 KiB. The OpenAI-compatible adapter retains its separate 64 KiB envelope limit.

| Route | Purpose |
| --- | --- |
| `POST /api/invoke` | Invoke an allowlisted business tool with validated arguments |
| `POST /api/models/complete` | Invoke an allowlisted Ollama model with a plain prompt or native messages |
| `GET /v1/models` | List model identifiers permitted for the verified role |
| `POST /v1/chat/completions` | Bounded OpenAI-compatible chat interface |
| `GET /acp/agents` | Discover configured ACP peers permitted for the caller |
| `POST /acp/runs` | Run a synchronous plain-text ACP peer through input/output controls |
| `GET /api/me` | Return trusted server-side identity claims |
| `GET /api/admin/status` | Management policy, budgets, telemetry and sanitized audit |
| `GET /api/admin/audit.jsonl` | Export retained sanitized records |

Business handlers are registered by your application. Start the downloadable [FastMCP server example](examples/fastmcp-server.md) on port 8010, then send this body to its `/api/invoke` endpoint with that example's agent credential:

```json
{
  "tool": "text.uppercase",
  "arguments": {"text": "hello"}
}
```

Actual model completions need a separately running Ollama server, an installed model and an active allowlisted model policy. Native `system`, `user` and `assistant` messages use Ollama `/api/chat`; plain prompts use `/api/generate`. Every message and stop sequence crosses the same input/output controls and resource accounting.

The OpenAI-compatible adapter supports bounded text messages, non-streaming responses, temperature zero and one completion. Requested completion tokens are clamped to the gateway ceiling and the active per-model policy. Streaming, generated tool calls, multimodal content, structured-output options and unsupported fields fail explicitly. `usage` is `null`, because conservative gateway budget units are not an exact provider billing split. Provider stop/length information and gateway decision metadata are retained.

## MCP

The Streamable HTTP MCP endpoint is `http://127.0.0.1:8000/mcp/`. It accepts verified agent credentials and exposes:

- The `invoke` tool, which accepts an allowlisted business-tool name and arguments.
- The `complete` tool, which accepts `model`, `prompt` and bounded `max_output_tokens`, and invokes the same model control path as HTTP.
- The `memory://{tenant}/{key}` resource, which calls the guarded `memory.read` operation.

The pinned MCP transport authenticates before JSON parsing and caps HTTP request bodies at 4 MiB. That protocol-envelope limit is separate from the smaller active-policy limit on actual model/tool input; protocol messages such as `ping` do not invoke a business operation.

Model completion through MCP requires an installed allowlisted model. Authored input/output rules, privacy, semantic checks, budgets and audit apply identically to HTTP. This server exposes registered operations rather than an unrestricted proxy for arbitrary MCP servers.

From your initialized package installation directory, save and run this complete Python client:

```python
import asyncio
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.client.auth import BearerAuth


async def main():
    credentials = json.loads(Path("state/credentials.json").read_text())
    async with Client(
        "http://127.0.0.1:8000/mcp/",
        auth=BearerAuth(credentials["local-agent"]),
    ) as client:
        completion = await client.call_tool(
            "complete", {"model": "qwen3:4b", "prompt": "Cat", "max_output_tokens": 16}
        )
        print(completion.data)


asyncio.run(main())
```

Existing installations retain their original credential file and identity names. If initialization reports the legacy `state/demo-tokens.json`, use its agent credential instead; do not rotate or overwrite credentials merely to rename them.

Tenant resources must match the verified identity. The policy pipeline runs before FastMCP creates its text and structured result representations, so both contain the filtered output.

## ACP peer agents

The Agent Communication Protocol compatibility endpoint is `/acp`. Configure
trusted peer addresses in `FASTFENCE_ACP_AGENTS`, then allowlist the corresponding
`acp.<alias>` tools and roles in policy. The [complete ACP example](examples/acp.md)
uses the official SDK to call a separate agent through FastFence.

This adapter supports synchronous, stateless, inline plain-text messages. It
rejects caller-selected sessions, streaming and attachments. Automatically generated peer session identifiers are discarded. Message text crosses the same input
and output controls as other tools; caller credentials never become peer credentials.
ACP has moved into A2A; this adapter preserves the documented ACP compatibility
profile and does not implement A2A.

## Actual Laya integration

The installed product uses the upstream [Laya Python engine](https://github.com/aayushch/laya) at a pinned revision. Normal `fastfence init` installs it in your installation directory and checks/downloads the configured assessment model through Ollama. Use `fastfence setup-laya` only for a separate engine installation or repair. This fetches the external engine, retains license notices and installs hash-verified dependencies into private local state. It requires Git, `sh` and `uv`; you do not need the FastFence repository.

Laya has two independent roles:

- **Runtime assessment:** named natural-language rules and security guidance inspect input/output content through the actual assessment model. Follow the complete [semantic policy client](examples/semantic-policy.md), which tests samples, displays a diff and activates only with explicit `--activate`.
- **Fast rule authoring:** **Describe a fast rule** drafts a bounded deterministic proposal, with content preview and generated regression cases. Review and activate it; later literal matching does not call Laya.

The default assessor is Qwen3:4b through local Ollama. Your protected completion model is configured independently. A precise letter restriction should use a literal/text rule; model judgment is approximate. See [policies](policies.md) for scope and failure behavior.

To connect an external agent, route its model client to the [OpenAI-compatible endpoint](examples/openai-client.md) and its registered operations through [FastMCP](examples/fastmcp-server.md). Installing a gateway does not intercept connectors that continue calling upstream services directly.
