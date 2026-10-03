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

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run [Ollama](https://ollama.com/) on macOS or Linux. In the directory where you want to keep your FastFence configuration, run:

```sh
uv tool run fastfence
```

From FastFence **1.0.2**, this command prepares the required runtime and starts the gateway. No separate `init` or `serve` step is needed. uv selects a compatible Python and caches the isolated package; `config/` and private `state/` stay in your current directory. Git and `sh` are needed for the pinned Laya installer. No FastFence checkout is required.

Already have an older version cached? Use `uv tool run fastfence@latest`. For a reproducible installation, use `uv tool run --python 3.12 fastfence@1.0.2`. The [installation guide](https://fastfence.dev/getting-started/) also covers pip and explicit provisioning commands.

Open **http://127.0.0.1:8000**, then **Connection**. Use `local-admin` from
`state/credentials.json` to manage policies and `local-agent` to make protected
requests. Tokens are randomly generated, private, and kept only in browser page
memory after you enter them. Management credentials cannot invoke agent operations.

The first launch creates your configuration and credentials, installs the pinned Laya engine,
downloads the configured assessment model if it is missing, and prepares OCR
dependencies and document models when needed. The fresh default
uses **Qwen3:4b** for assessment and protected completions, as separate calls, so
one model download is enough. Your application's completion model can be changed
independently. Tool-only and ACP integrations need no separate completion model.

Laya checks input and output that reach semantic inspection. Missing or failed
assessment blocks the request; local rules run before it. Restarting the command
preserves valid existing configuration and keys. For configuration provisioning
without downloads, use `uv tool run --python 3.12 fastfence@1.0.2 init --config-only`; normal
initialization must finish before model-backed protection is ready.

OCR of images and multipage PDFs is prepared automatically. For a separate repair or diagnostic check:

```sh
uv tool run --python 3.12 fastfence@1.0.2 setup-ocr
uv tool run --python 3.12 fastfence@1.0.2 doctor --full
```

Restart after repairing components or changing `.env`. OCR converts
attachments into inspected Markdown; it does not modify image or PDF pixels.

## Make a protected request

This reads your local agent credential without writing it into shell history:

```sh
uv run --no-project --python 3.12 --with httpx python - <<'PY'
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

Stop the gateway, then explicitly refresh the tool to the latest published release:

```sh
uv tool run fastfence@latest
```

Pinned `@1.0.2` commands remain on that version. With pip, activate your environment and use `python -m pip install --upgrade fastfence` before restarting.

Reload the browser. Your working directory's configuration and private state are independent of the installed package; preserve and back them up. Initialization is repeatable and retains valid existing credentials and keys.

Download [runnable examples](https://fastfence.dev/downloads/fastfence-examples.zip), extract them into `examples/` in your installation directory, and run `uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/protected_request.py --prompt 'Hello'`. The documentation embeds the complete source for REST, named Laya policies, FastMCP, OpenAI SDK and public/private-key anonymization.

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

Licensed under [Apache 2.0](https://github.com/llama-lovers/FastFence/blob/main/LICENSE); see [NOTICE](https://github.com/llama-lovers/FastFence/blob/main/NOTICE). Dependencies retain their
own licenses. Documentation uses MkDocs Material and GitHub Pages at **fastfence.dev**.
