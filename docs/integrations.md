# Integrations

FastFence protects operations routed through its gateway. Existing agent connectors need explicit routing through the protected adapters; installing FastFence does not automatically intercept an agent's other network traffic.

## REST tools and models

Agent routes require a provisioned agent bearer credential. Management routes require a separate management credential. The interactive local API schema is available at `http://127.0.0.1:8000/docs`.

| Route | Purpose |
| --- | --- |
| `POST /api/invoke` | Invoke an allowlisted business tool with validated arguments |
| `POST /api/models/complete` | Invoke an allowlisted Ollama model with a plain prompt or native messages |
| `GET /v1/models` | List model identifiers permitted for the verified role |
| `POST /v1/chat/completions` | Bounded OpenAI-compatible chat interface |
| `GET /api/me` | Return trusted server-side identity claims |
| `GET /api/admin/status` | Management policy, budgets, telemetry and sanitized audit |
| `GET /api/admin/audit.jsonl` | Export retained sanitized records |

A business-tool request has this shape:

```json
{
  "tool": "knowledge.search",
  "arguments": {"query": "Quarterly forecast"}
}
```

Actual model completions need a separately running Ollama server, an installed model and an active allowlisted model policy. Native `system`, `user` and `assistant` messages use Ollama `/api/chat`; plain prompts use `/api/generate`. Every message and stop sequence crosses the same input/output controls and resource accounting.

The OpenAI-compatible adapter supports bounded text messages, non-streaming responses, temperature zero and one completion. Requested completion tokens are clamped to the gateway ceiling and the active per-model policy. Streaming, generated tool calls, multimodal content, structured-output options and unsupported fields fail explicitly. `usage` is `null`, because conservative gateway budget units are not an exact provider billing split. Provider stop/length information and gateway decision metadata are retained.

## MCP

The Streamable HTTP MCP endpoint is `http://127.0.0.1:8000/mcp/`. It accepts verified agent credentials and exposes:

- The `invoke` tool, which accepts an allowlisted business-tool name and arguments.
- The `complete` tool, which accepts `model`, `prompt` and bounded `max_output_tokens`, and invokes the same model control path as HTTP.
- The `memory://{tenant}/{key}` resource, which calls the guarded `memory.read` operation.

Model completion through MCP requires an installed allowlisted model. Authored input/output rules, privacy, semantic checks, budgets and audit apply identically to HTTP. This server exposes registered operations rather than an unrestricted proxy for arbitrary MCP servers.

From a locally initialized checkout:

```python
import asyncio
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.client.auth import BearerAuth


async def main():
    credentials = json.loads(Path("state/demo-tokens.json").read_text())
    async with Client(
        "http://127.0.0.1:8000/mcp/",
        auth=BearerAuth(credentials["analyst-blue"]),
    ) as client:
        result = await client.call_tool(
            "invoke",
            {"tool": "knowledge.search", "arguments": {"query": "Forecast"}},
        )
        print(result.data)
        print(await client.read_resource("memory://blue/forecast"))
        completion = await client.call_tool(
            "complete", {"model": "qwen3:0.6b", "prompt": "Cat", "max_output_tokens": 16}
        )
        print(completion.data)


asyncio.run(main())
```

Tenant resources must match the verified identity. The policy pipeline runs before FastMCP creates its text and structured result representations, so both contain the filtered output.

## Actual Laya integration

The repository runs the real upstream [Laya Python engine](https://github.com/aayushch/laya) at a pinned revision. Setup retains upstream license notices and installs hash-verified dependencies into gitignored local state; it does not vendor the engine into FastFence.

With initialized gateway credentials, a running Ollama model and the [hybrid policy](policies.md) active:

```sh
integrations/laya/setup.sh
integrations/laya/run-demo.sh
```

The runner invokes Laya's actual `llm_call` through its custom OpenAI-compatible provider, then registers a `fastfence_invoke` handler in Laya's actual tool-dispatch registry. That handler sends business operations to `/api/invoke`.

| Path | Demonstrated protection |
| --- | --- |
| Laya model client → FastFence chat route → Ollama | Actual model inference with gateway input/output controls |
| Laya `fastfence_invoke` handler → FastFence tool route | Allowed search, RBAC denial and cross-tenant denial |
| Other native Laya connectors | Not automatically intercepted by this demonstration |

All five recorded cases passed: a real model response, model-injection denial, allowed business search, unauthorized payment-preparation denial and cross-tenant memory denial. Business handlers use simulated gateway data; the demo performs no real payments or external account operations.

The runner creates temporary Laya configuration and audit storage without changing the user's Laya configuration or connecting Gmail, Slack or n8n accounts. Laya's temporary SQLite usage belongs to the external agent; FastFence's enforcement ledger remains memory-only. Generated reports omit prompts, generated text, credentials and request bodies.

See the [full integration instructions](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/integrations/laya/README.md) and [sanitized live report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/integrations/laya/results/live.json), subject to the project repository's access permissions. A full deployment must route relevant native handlers through the gateway and control network egress so an agent cannot bypass it.

## Laya as a rule author

The dashboard now provides [natural-language policy drafting](policies.md#describe-a-policy-in-the-dashboard), including text restrictions, selective privacy actions and tool-role restrictions. It requires exact review, content preview and explicit activation.

The separate `integrations/laya/author-rule.sh` CLI uses actual Laya model inference to draft bounded text restrictions. It validates and previews the result through management endpoints, then optionally saves a private proposal. Activate that exact proposal with `--proposal ... --activate`; the activation step makes no model call.

This is management-side authoring, separate from the protected agent demonstration above. It uses a trusted local Ollama endpoint directly and a process-local compatibility adapter for structured output. Read the [complete natural-language authoring workflow](policies.md#draft-a-rule-in-natural-language-with-laya). Runtime enforcement remains local and model-independent; broader semantic, legal or compliance instructions are outside this DSL.

## Real business backends

The current knowledge, contact, memory and payment-preparation handlers are simulated. To connect a real backend, implement its validated allowlisted handler behind the tools port and keep backend credentials on the gateway side. Callers cannot select upstream URLs or supply upstream credentials.

Output blocking cannot reverse an executed business operation. Irreversible operations need their own transaction or approval design in addition to gateway policy checks.

## Trace a protected call

Every gateway verdict carries a request ID. In the dashboard, paste it into the decision-trail search and open **Details** to inspect matched rule IDs, policy/feed versions and whether the upstream executed. Playground results offer **View this decision in audit** directly. The UI searches its latest loaded 200 events; use the management audit export for the complete retained ring. Audit details contain sanitized metadata, not prompt or response bodies.
