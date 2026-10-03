# Getting started

## Run the deterministic demo

Use macOS or Linux, Python 3.12, and [uv](https://docs.astral.sh/uv/). Run these commands from the repository root:

```sh
git clone https://github.com/llama-lovers/HackYeah2026-challenge-second.git
cd HackYeah2026-challenge-second
uv sync --locked
uv run fastfence init
uv run fastfence serve
```

Open **http://127.0.0.1:8000**. In **Connect identities**, enter the locally generated `analyst-blue` and `security-admin` tokens from `state/demo-tokens.json`. The file is private and Git-ignored. Tokens stay in dashboard page memory; there is no public default credential.

Initialization creates startup identity records and demo tokens once. If the state already exists, keep those credentials and skip `init`. Management tokens can inspect and edit policy but cannot invoke agent tools.

In a second terminal, run:

```sh
uv run fastfence demo
```

The demo exercises allowed search, blocked injection and sensitive input, role denial, cross-tenant denial, output redaction, and authorized simulated payment preparation. Requests consume the real instance budget, so repeated demonstrations can exhaust the configured allowance.

## Try a request

Set `FASTFENCE_AGENT_TOKEN` in your shell to your own `analyst-blue` token. Keep the value out of source files, screenshots, and shared shell history.

```sh
curl http://127.0.0.1:8000/api/invoke \
  -H "Authorization: Bearer ${FASTFENCE_AGENT_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"tool":"knowledge.search","arguments":{"query":"Quarterly forecast"}}'
```

The response includes the decision, reason, request ID, active policy/feed versions, and whether upstream execution occurred. For a deterministic negative case, replace the query with `Ignore all previous instructions`; the supplied signature feed blocks it before execution.

Interactive HTTP schemas are at **http://127.0.0.1:8000/docs**. The dashboard and API are part of the running gateway; this documentation site does not host a gateway or accept credentials.

## Describe a rule, then test it through MCP

After the deterministic setup above, start Ollama and install both local models plus the pinned Laya engine:

```sh
ollama pull qwen3:4b
ollama pull qwen3:0.6b
integrations/laya/setup.sh
```

`qwen3:4b` drafts the policy through Laya. `qwen3:0.6b` answers the protected completion request. Keep the default policy for this example: semantic assessment can remain disabled because the authored text rule runs locally. If Ollama is not running, start its app or run `ollama serve` in another terminal.

In the connected dashboard at **http://127.0.0.1:8000**:

1. Open **Describe a policy** and enter: `Blokuj każde słowo zawierające literę a wyłącznie w wejściu modeli, bez rozróżniania wielkości liter.`
2. Draft with Laya. Inspect the operation: the text rule should use `word_contains`, literal `a`, input direction and model target, with case-insensitive matching. Redraft if the model interpreted the instruction differently.
3. Preview `Hello` and `Cat` on separate lines, with input direction and model target. Expect `NO_LOCAL_MATCH` for `Hello` and `BLOCKED` for `Cat`. Preview checks local content controls; full requests also check permissions and budgets.
4. Confirm review and activate the proposal. The policy version increments; activation and subsequent rule matching do not call the authoring model.

From the repository root, make two real MCP requests:

```sh
uv run python - <<'PYTHON'
import asyncio
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.client.auth import BearerAuth


async def main():
    tokens = json.loads(Path("state/demo-tokens.json").read_text())
    async with Client(
        "http://127.0.0.1:8000/mcp/",
        auth=BearerAuth(tokens["analyst-blue"]),
    ) as client:
        for prompt in ("Cat", "Hi"):
            result = await client.call_tool(
                "complete",
                {"model": "qwen3:0.6b", "prompt": prompt, "max_output_tokens": 16},
            )
            print(prompt, result.data)


asyncio.run(main())
PYTHON
```

`Cat` must return a blocked decision with `upstream_executed: false`. `Hi` passes this input rule and reaches Qwen if the other active controls and budget permit it. Its generated text is model-dependent. Find both request IDs in the dashboard audit to confirm which policy and rule made each decision.

This example deliberately restricts **input**. To protect generated words too, request input **and output** in the instruction and review that scope before activation. Then an allowed prompt can still produce a blocked answer; the audit records `upstream_executed: true` for an output-side denial.

## Add a local Qwen model

The default policy allowlists `qwen3:0.6b` for completion but disables semantic analysis. Completion still requires a running Ollama service and installed model.

To demonstrate actual hybrid analysis with Qwen3:4b, start [Ollama](https://docs.ollama.com/), stop FastFence, and run:

```sh
ollama pull qwen3:4b
cp config/policy.yaml config/policy.backup.yaml
cp config/policy.hybrid.yaml config/policy.yaml
uv run fastfence serve
```

This profile enables Ollama semantic checks and allowlists Qwen3:4b. For a live update instead of a restart, the replacement policy must have a version higher than the current one. An invocation retains the snapshot it started with.

You can now call the protected model endpoint:

```sh
curl http://127.0.0.1:8000/api/models/complete \
  -H "Authorization: Bearer ${FASTFENCE_AGENT_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:4b","prompt":"Summarize the purpose of a quarterly forecast.","max_output_tokens":64}'
```

The completion model must be installed and present in `policy.models` with a role matching your identity. `semantic.model` selects the separate security assessor; it does not automatically grant access to a completion model. The default upstream address is `http://127.0.0.1:11434`, configurable only by trusted server settings.

See [integrations](integrations.md) for MCP, OpenAI-compatible clients, and the actual Laya runner. See [testing](testing.md) to verify the installation without a running LLM.
