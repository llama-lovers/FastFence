# Integration reference

FastFence enforces controls on operations routed through it. It does not intercept an agent's unrelated network calls. Choose an adapter explicitly and keep agent credentials separate from management access.

## Protocols

| Surface | Endpoint | Intended client |
| --- | --- | --- |
| Protected model REST | `POST /api/models/complete` | Clients that need the complete FastFence verdict |
| Protected tool REST | `POST /api/invoke` | Applications with registered tool implementations |
| OpenAI-compatible text chat | `/v1/chat/completions`, `/v1/models` | Clients supporting a custom API base URL |
| MCP | `/mcp/` | Streamable HTTP MCP clients |
| Document processing | See the [HTTP inventory](reference/http-api.md) | Upload and protected Markdown workflows |
| Management | `/api/admin/…` | Console or trusted policy administration |

The [HTTP inventory](reference/http-api.md) is generated from source on each site build. A running gateway exposes exact request and response schemas at `/openapi.json` and an interactive explorer at `/docs`.

## Identity and response handling

Pass a provisioned token in `Authorization: Bearer …`. The server supplies trusted roles and tenant claims from the identity configuration; callers cannot grant themselves roles in a request body. Management routes additionally require a management identity.

Protected REST invocations return a security verdict. Inspect `decision`, `reason`, `findings`, `policy_version` and `upstream_executed`. **HTTP 200 alone is not an allow decision.** An input block prevents upstream execution; an output block suppresses an already generated result and cannot roll back upstream side effects.

The console keeps credentials in page memory. A page reload requires reconnection. Audit records contain bounded decision metadata rather than raw prompts or responses.

## MCP

Connect to `http://127.0.0.1:8000/mcp/` with your agent bearer identity. The server exposes `complete` for protected model calls, `invoke` for registered tools, and the guarded tenant-memory resource. Tool and memory operations require actual implementations and matching policy permissions; their presence in the protocol is not a promise of a default business backend.

This is a server of registered protected operations, not an unrestricted forwarding proxy for arbitrary third-party MCP servers. See [MCP client examples](integrations.md#mcp).

## OpenAI-compatible chat

Set the client base URL to `http://127.0.0.1:8000/v1` and supply an agent credential. Supported chat uses bounded text messages, one non-streaming completion and temperature zero. The allowed models come from the active policy and verified identity.

Streaming, generated tool calls, multimodal message content and unsupported structured-output options are rejected. The compatibility response uses `usage: null`; FastFence's conservative budget units are not a provider billing breakdown. See the [detailed adapter behavior](integrations.md#rest-tools-and-models).

## Policy authoring and configuration

Laya authoring has three separate operations: draft a bounded proposal, preview its local behavior against reviewed expectations, and activate the stored proposal. Activation uses the exact saved proposal without a second model inference. It is a management operation, not part of normal request enforcement.

Local configuration lives in YAML/JSON files. A configured trusted HTTP bundle is read-only through local management writes. Invalid configuration preserves the last valid snapshot. See [policies](policies.md) and [settings](settings.md).

## Test a named Laya rule

`POST /api/admin/semantic/preview` assesses a candidate named rule against a sample using actual Laya. It requires a management identity, includes the current applicable semantic rules and does not activate the candidate. This is separate from `/api/admin/policies/preview`, which tests a generated configuration proposal against local controls.

With the gateway and Laya running, set `FASTFENCE_MANAGEMENT_TOKEN` to your own management credential and run from your installation directory:

```python
import json
import os

import httpx

headers = {"Authorization": "Bearer " + os.environ["FASTFENCE_MANAGEMENT_TOKEN"]}
with httpx.Client(base_url="http://127.0.0.1:8000", headers=headers, timeout=65) as client:
    current = client.get("/api/admin/status")
    current.raise_for_status()
    candidate = {
        "base_version": current.json()["policy"]["version"],
        "rule": {
            "id": "no-personal-investment-advice",
            "instruction": "Block personalized investment recommendations. Allow general financial education.",
            "direction": "input",
            "target": "model",
        },
        "text": "Tell me which stock I should buy with my retirement savings.",
        "direction": "input",
        "target": "model",
    }
    result = client.post("/api/admin/semantic/preview", json=candidate)
    result.raise_for_status()
    print(json.dumps(result.json(), indent=2))
```

Save this as a local Python file and execute it with `python <file>` in your activated FastFence virtual environment. The response includes `decision` (`blocked` or `no_semantic_block`), `semantic_score`, `provider`, `model`, `rule_applied`, `base_version` and `latency_ms`. The sample is limited to 4,096 characters. Change the outer `direction`/`target` to test other combinations; `rule_applied: false` means this candidate was outside that scope, while the existing applicable security instructions can still produce a block.

A stale base version returns `409`; invalid candidate configuration returns `422`; unavailable or busy analysis returns `503`. Refresh the active version and retry deliberately. The score reflects the combined semantic context rather than a matched-rule attribution. `no_semantic_block` is not a full runtime allow decision: this endpoint does not test agent permissions, budgets, local privacy controls or upstream behavior. It does count the assessment in semantic-call telemetry.

For publication, use the console's tested-rule review flow or a versioned complete-policy update. Preview alone never changes the active policy.

## Limits and deployment assumptions

Budgets, audit retention and replay-related runtime behavior are scoped to one process. Multiple independent gateway processes do not share a global spending ledger. Reversible anonymization depends on configured keys and complete authenticated tokens; irreversible masking cannot recover originals.

Local OCR produces protected Markdown and supports multipage PDF input. It does not preserve document layout, edit files or produce redacted PDF/image artifacts. See [architecture](architecture.md) and [manual verification](manual-testing.md) for current behavior and reproducible checks.

## Startup identity capacity

The local registry defaults to **4096 identities including administrators** and a **1 MiB** file/inline JSON limit. These bound startup memory; they do not measure concurrent model capacity. Authentication indexes credential digests in memory.

For example, to provision 5000 callers plus administrators, set these in the installation's `.env` and restart:

```dotenv
FASTFENCE_IDENTITY_MAX_RECORDS=8192
FASTFENCE_IDENTITY_MAX_SOURCE_BYTES=4194304
```

Provision the identity records separately. These settings do not create accounts. Hard bounds are 65,536 records and 64 MiB; both limits apply independently. Duplicate subjects and credential hashes are rejected. Budgets and audit remain process-local; increasing registry capacity does not share state across workers or increase Laya inference throughput.

## Runtime admission limits

Each business-model HTTP adapter reuses a pool of up to **32 connections** and admits at most **128 active or waiting requests**. Waiting for a connection consumes the request's existing deadline. Upstream cookies are neither retained nor forwarded between calls.

The local Laya worker evaluates **one assessment at a time**, with at most **32 active or waiting assessments**. Queue time also counts toward the configured semantic timeout. Requests beyond these limits fail closed; increasing the account registry does not change them. A protected chat can require input assessment, model generation and output assessment, so account count is not a throughput estimate.

A burst of 1000 concurrent conversations on one local model is not a supported capacity claim. Measure the complete application/gateway/model path with your prompt sizes, expected output lengths and both allowed and blocked traffic. The [benchmarks](benchmarks.md) separate local controls from inference; they are not a multi-user service SLO.
