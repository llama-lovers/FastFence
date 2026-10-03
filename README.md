# FastFence

**Security policies between your agents and their models or tools.**

FastFence is a local AI control layer with authenticated HTTP, OpenAI-compatible,
MCP and synchronous text ACP interfaces. It combines deterministic rules with real Laya/Qwen text
assessment, applies input and output controls, reserves per-identity resource
budgets, and records sanitized decisions. The management console lets you review
policy changes, test requests and inspect activity.

[Documentation](https://fastfence.dev/) · [Getting started](https://fastfence.dev/getting-started/) ·
[Manual testing](https://fastfence.dev/manual-testing/) · [API reference](https://fastfence.dev/integration-reference/)

## Run locally

Requirements: macOS or Linux, Python 3.12 and a running [Ollama](https://ollama.com/) service. Git and `sh` are needed by the installer for the pinned external Laya engine; no FastFence checkout is needed.

```sh
mkdir fastfence-local
cd fastfence-local
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install fastfence uv
fastfence init --anonymization
fastfence doctor
fastfence serve
```

Open **http://127.0.0.1:8000**, then **Connection**. Use `local-admin` from
`state/credentials.json` to manage policies and `local-agent` to make protected
requests. Tokens are randomly generated, private, and kept only in browser page
memory after you enter them. Management credentials cannot invoke agent operations.

`init` creates your configuration and credentials, installs the pinned Laya engine,
and downloads the configured assessment model if it is missing. The fresh default
uses **Qwen3:4b** for assessment and protected completions, as separate calls, so
one model download is enough. Your application's completion model can be changed
independently. Tool-only and ACP integrations need no separate completion model.

Laya checks input and output that reach semantic inspection. Missing or failed
assessment blocks the request; local rules run before it. Repeating `init`
preserves valid existing configuration and keys. For configuration provisioning
without downloads, use `fastfence init --config-only --anonymization`; normal
initialization must finish before model-backed protection is ready.

For OCR of images and multipage PDFs:

```sh
fastfence setup-ocr
fastfence doctor --full
```

Restart after installing optional components or changing `.env`. OCR converts
attachments into inspected Markdown; it does not modify image or PDF pixels.

## Make a protected request

This reads your local agent credential without writing it into shell history:

```sh
python - <<'PY'
import json
from pathlib import Path
import httpx

credentials = json.loads(Path("state/credentials.json").read_text())
response = httpx.post(
    "http://127.0.0.1:8000/api/models/complete",
    headers={"Authorization": "Bearer " + credentials["local-agent"]},
    json={"model": "qwen3:4b", "prompt": "Hello", "max_output_tokens": 256},
    timeout=120,
)
response.raise_for_status()
print(response.json())
PY
```

The result includes the decision, reason, request ID, active policy version,
semantic provider/score and whether the completion model ran. Find that request
in **Activity**. MCP clients connect to `http://127.0.0.1:8000/mcp/`; OpenAI clients
use `http://127.0.0.1:8000/v1` with the same agent token. See [integration examples](https://fastfence.dev/integrations/).

## Change a policy

1. Open **Policies** and edit configuration or describe a rule in your own words.
2. For a Laya-authored rule, inspect its scope, proposed changes and generated tests.
3. Review the diff, run the tests and activate the reviewed version.
4. Try your own inputs in **Test requests** and inspect the recorded decisions.

Laya has two roles: it drafts reviewable deterministic rules and assesses actual
request/response text when `semantic.provider: laya` is active. Trusted natural-language
assessment instructions belong in `semantic.instructions`. A precise restriction
such as forbidden letters should use a deterministic text rule; model judgments
are approximate and need evaluation for your policy.

The active policy is `config/policy.yaml`; valid higher versions hot-reload without
restarting. `.env` contains deployment settings. Reviewed generated tests are saved
in `config/policy-tests.yaml`. Invalid updates retain the last valid snapshot.

For peer-agent communication, configure a trusted ACP agent and use
`http://127.0.0.1:8000/acp`. The [ACP example](https://fastfence.dev/examples/acp/)
includes an official SDK client and a separate local agent.

## Connect business tools

The product includes **no simulated business handlers**. Implement `ToolsPort`,
inject the adapter with `create_app(settings, tools=adapter)`, and allowlist its
operations and roles in policy. An allowlist without a connected adapter fails closed.

The downloadable [FastMCP server example](https://fastfence.dev/examples/fastmcp-server/)
connects an actual uppercase tool through this port. It uses a separate server,
policy and credentials; replace its operation with your application logic.

## Update and verify

Stop the gateway, activate its virtual environment, then run:

```sh
python -m pip install --upgrade fastfence
fastfence doctor
fastfence serve
```

Reload the browser. Your working directory's configuration and private state are independent of the installed package; preserve and back them up. Initialization is repeatable and retains valid existing credentials and keys.

Download [runnable examples](https://fastfence.dev/downloads/fastfence-examples.zip), extract them into `examples/` in your installation directory, and run `python examples/protected_request.py --prompt 'Hello'`. The documentation embeds the complete source for REST, named Laya policies, FastMCP, OpenAI SDK and public/private-key anonymization.

Follow [the installation checks](https://fastfence.dev/manual-testing/) to verify your own models, policies and documents.

## Operating scope

Budgets and audit retention are bounded, in-memory and per process. Restarting clears
them; replicas do not share a global quota. Identity configuration and optional
anonymization keys are startup inputs, not a conversation database. Reversible
anonymization requires an intact authenticated token, the correct key and explicit
restoration permission. Keep keys and credentials private and backed up.

Model judgments can miss attacks or block legitimate text. Deterministic checks cover
specific configured patterns, permissions and limits, not universal attack detection.
Irreversible business actions require adapter-specific authorization and transaction
controls. [Architecture](https://fastfence.dev/architecture/) · [Policies](https://fastfence.dev/policies/) ·
[Settings](https://fastfence.dev/settings/).

Licensed under [Apache 2.0](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/LICENSE); see [NOTICE](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/NOTICE). Dependencies retain their
own licenses. Documentation uses MkDocs Material and GitHub Pages at **fastfence.dev**.
