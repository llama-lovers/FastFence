# FastFence

**Security policies between your agents and their models or tools.**

FastFence is a local AI control layer with authenticated HTTP, OpenAI-compatible
and MCP interfaces. It combines deterministic rules with real Laya/Qwen text
assessment, applies input and output controls, reserves per-identity resource
budgets, and records sanitized decisions. The management console lets you review
policy changes, test requests and inspect activity.

[Documentation](https://fastfence.dev/) · [Getting started](docs/getting-started.md) ·
[Manual testing](docs/manual-testing.md) · [API reference](docs/integration-reference.md)

## Run locally

Requirements: macOS or Linux, Git, Python 3.12, [uv](https://docs.astral.sh/uv/),
and a running [Ollama](https://ollama.com/) service.

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

Open **http://127.0.0.1:8000**, then **Connection**. Use `local-admin` from
`state/credentials.json` to manage policies and `local-agent` to make protected
requests. Tokens are randomly generated, private, and kept only in browser page
memory after you enter them. Management credentials cannot invoke agent operations.

The default policy uses **Laya with Qwen3:4b to assess input and output text**;
Qwen3:0.6b is the separate protected completion model. Missing or failed assessment
blocks the request. Nothing silently substitutes a deterministic-only classifier.
Model assessment adds inference latency; local rules run before it.

For OCR of images and multipage PDFs:

```sh
sh scripts/setup-ocr.sh
uv run fastfence doctor --full
```

Restart after installing optional components or changing `.env`. OCR converts
attachments into inspected Markdown; it does not modify image or PDF pixels.

## Make a protected request

This reads your local agent credential without writing it into shell history:

```sh
uv run python - <<'PY'
import json
from pathlib import Path
import httpx

credentials = json.loads(Path("state/credentials.json").read_text())
response = httpx.post(
    "http://127.0.0.1:8000/api/models/complete",
    headers={"Authorization": "Bearer " + credentials["local-agent"]},
    json={"model": "qwen3:0.6b", "prompt": "Hello", "max_output_tokens": 64},
    timeout=120,
)
response.raise_for_status()
print(response.json())
PY
```

The result includes the decision, reason, request ID, active policy version,
semantic provider/score and whether the completion model ran. Find that request
in **Activity**. MCP clients connect to `http://127.0.0.1:8000/mcp/`; OpenAI clients
use `http://127.0.0.1:8000/v1` with the same agent token. See [integration examples](docs/integrations.md).

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

## Connect business tools

The product includes **no simulated business handlers**. Implement `ToolsPort`,
inject the adapter with `create_app(settings, tools=adapter)`, and allowlist its
operations and roles in policy. An allowlist without a connected adapter fails closed.

[The opt-in business-tools example](examples/business_tools/README.md) runs simulated
search, tenant memory and payment preparation in a separate server and state directory.
It illustrates adapter composition and does not handle real payments.

## Update and verify

Stop the gateway, then run `git pull`, `uv sync --locked`, and `uv run fastfence serve`.
Reload the browser. Preserve your configuration changes when resolving Git conflicts.
Initialization is repeatable and never rotates valid existing credentials or keys.
Older installations retain `state/demo-tokens.json` and its `security-admin` /
`analyst-blue` identities; these remain supported.

```sh
uv run pytest -q
uv run pre-commit run --all-files
uv run python scripts/smoke_clean_install.py --full
```

The full clean-install check requires running Ollama and installs fresh feature
environments. Its no-argument CI mode explicitly selects the documented offline
profile; it does not claim to test model inference. [Validation details](docs/testing.md).

## Operating scope

Budgets and audit retention are bounded, in-memory and per process. Restarting clears
them; replicas do not share a global quota. Identity configuration and optional
anonymization keys are startup inputs, not a conversation database. Reversible
anonymization requires an intact authenticated token, the correct key and explicit
restoration permission. Keep keys and credentials private and backed up.

Model judgments can miss attacks or block legitimate text. Deterministic checks cover
specific configured patterns, permissions and limits, not universal attack detection.
Irreversible business actions require adapter-specific authorization and transaction
controls. [Architecture](docs/architecture.md) · [Policies](docs/policies.md) ·
[Settings](docs/settings.md) · [Evaluation](docs/testing.md).

Licensed under [Apache 2.0](LICENSE); see [NOTICE](NOTICE). Dependencies retain their
own licenses. Documentation uses MkDocs Material and GitHub Pages at **fastfence.dev**.
