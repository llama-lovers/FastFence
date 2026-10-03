# Getting started

## Start your local gateway

Use macOS or Linux, Python 3.12, [uv](https://docs.astral.sh/uv/), and a running [Ollama](https://ollama.com/) service. Run these commands from the repository root:

```sh
git clone https://github.com/llama-lovers/HackYeah2026-challenge-second.git
cd HackYeah2026-challenge-second
uv sync --locked
uv run fastfence init --anonymization
sh integrations/laya/setup.sh
ollama pull qwen3:4b
ollama pull qwen3:0.6b
uv run fastfence doctor
uv run fastfence serve
```

Open **http://127.0.0.1:8000**. In **Connection**, enter the locally generated `local-agent` and `local-admin` tokens from `state/credentials.json`. The file is private and Git-ignored. Tokens stay in dashboard page memory; there is no public default credential.

Initialization creates one local agent identity, one management identity and an optional private anonymization keyring. Repeating `init --anonymization` validates and preserves existing valid credentials and keys. Management tokens can inspect and edit policy but cannot invoke agent tools.

Existing installations keep their original valid credentials. If you have
`state/demo-tokens.json`, use its `security-admin` and `analyst-blue` values.
Do not delete private state to upgrade. The default runtime has no business tool
backend; simulated business tools are available only through the
[explicit example](https://github.com/llama-lovers/HackYeah2026-challenge-second/tree/main/examples/business_tools).

## Add document OCR

Use the [fresh-install manual](manual-testing.md) for the complete ordered setup.
Install the optional OCR interpreter and model files:

```sh
sh scripts/setup-ocr.sh
uv run fastfence doctor --full
```

Restart the gateway after setup. The standard OCR interpreter/models and private
keyring are discovered automatically; the install does not require someone
else's `.env` or private state. If `doctor --full` fails, follow its specific
prerequisite command before proceeding.

## Try a request

Set `FASTFENCE_AGENT_TOKEN` in your shell to your own `local-agent` token. Keep the value out of source files, screenshots, and shared shell history.

```sh
curl http://127.0.0.1:8000/api/models/complete \
  -H "Authorization: Bearer ${FASTFENCE_AGENT_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3:0.6b","prompt":"Explain access control briefly.","max_output_tokens":64}'
```

The response includes the decision, reason, request ID, active policy/feed versions, and whether upstream execution occurred. For a deterministic negative case, replace the prompt with `Ignore all previous instructions`; the supplied signature feed blocks it before execution.

Interactive HTTP schemas are at **http://127.0.0.1:8000/docs**. The dashboard and API are part of the running gateway; this documentation site does not host a gateway or accept credentials.

## Describe a rule, then test it through MCP

After the core setup above, start Ollama and install both local models plus the pinned Laya engine:

```sh
ollama pull qwen3:4b
ollama pull qwen3:0.6b
integrations/laya/setup.sh
```

`qwen3:4b` drafts policy and assesses actual text through Laya. `qwen3:0.6b` answers the protected completion request. Keep the default policy for this example: the authored text rule runs locally before the separately enabled Laya assessment. If Ollama is not running, start its app or run `ollama serve` in another terminal.

In the connected dashboard at **http://127.0.0.1:8000**:

1. Open **Policies → Describe a policy** and enter: `Blokuj każde słowo zawierające literę a wyłącznie w wejściu modeli, bez rozróżniania wielkości liter.`
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
    tokens = json.loads(Path("state/credentials.json").read_text())
    async with Client(
        "http://127.0.0.1:8000/mcp/",
        auth=BearerAuth(tokens["local-agent"]),
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

`Cat` must return a blocked decision with `upstream_executed: false`. `Hi` passes this input rule and reaches Qwen if the other active controls and budget permit it. Its generated text is model-dependent. Find both request IDs in the **Activity** to confirm which policy and rule made each decision.

This example deliberately restricts **input**. To protect generated words too, request input **and output** in the instruction and review that scope before activation. Then an allowed prompt can still produce a blocked answer; the audit records `upstream_executed: true` for an output-side denial.

## Add a local Qwen model

The default policy allowlists `qwen3:0.6b` for completion and uses Laya/Qwen3:4b to assess input and output text. Completion still requires a running Ollama service and installed model.

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

## Update FastFence and your policies

For a product update, stop your running gateway, then run:

```sh
git pull
uv sync --locked
uv run fastfence doctor
uv run fastfence serve
```

The console served at the local gateway URL is updated with the application; reload
your browser after restart. Private credentials, keys and policy edits are retained.
If Git reports local configuration conflicts, preserve and reconcile your policy
changes before restarting; never reset the repository to discard them.

For policy-only changes, use the console policy editor. Review the changes and
activate a version higher than the current version. The updated policy applies
to new requests immediately without restarting FastFence. File edits in
`config/policy.yaml` also hot-reload when valid and higher-version; invalid changes
leave the last valid snapshot active. `.env` settings require a restart.

## Explicit offline checks

For deterministic-only development or CI with no model service, select the offline
profile in a separate test checkout before starting the gateway:

```sh
cp config/policy.offline.yaml config/policy.yaml
uv run fastfence serve
```

This intentionally disables semantic assessment. It does not provide the default
product's Laya text assessment and cannot make successful model completions without
a model service. Do not overwrite an existing customized policy to run this test.
