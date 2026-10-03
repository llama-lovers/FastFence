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
