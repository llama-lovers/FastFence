# Getting started

## Install FastFence

Use macOS or Linux and **Python 3.12**. Create a directory for your local installation; configuration and private state will live here. You do not need the FastFence source repository.

```sh
mkdir fastfence-local
cd fastfence-local
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install fastfence uv
```

## Initialize and start

Install [Ollama](https://ollama.com/) and start its service before initialization (`ollama serve` in another terminal, or the running desktop app). Keep Git and `sh` available so initialization can fetch the pinned Laya engine.

```sh
fastfence init --anonymization
fastfence doctor
fastfence serve
```

Open **http://127.0.0.1:8000**. In **Connection**, enter the `local-agent` and `local-admin` tokens from your private `state/credentials.json`. Agent credentials send protected requests; management credentials review and change policies. Tokens stay in dashboard page memory.

Initialization creates `config/`, private credentials and the optional anonymization issuer keyring in your working directory. It also installs the pinned Laya engine and checks Ollama for the active policy's assessment model, downloading that model only when missing. Repeating `init --anonymization` preserves valid existing credentials, policies and keys. Keep this directory when upgrading. Older installations with `state/demo-tokens.json` retain their `security-admin` and `analyst-blue` identities.

There are three separate roles:

- **Laya** is the Python engine that runs security assessments and helps draft rules. `init` installs it.
- **The assessment model** interprets the text being checked. The default is **Qwen3:4b**, served by Ollama. `init` checks and downloads the configured assessor.
- **Your application's model or tool** performs the requested work after input checks. The fresh policy also allows Qwen3:4b for completions, so the quickstart needs one model download. Choose another allowlisted model or an [OpenAI-compatible upstream](examples/openai-upstream.md) when your application needs it.

Assessment and completion are separate calls even when they use the same model. An agent that only calls tools or ACP peers does not need a separate completion model. Initialization preserves an existing model choice and does not download an extra business model. Missing assessment fails closed; precise literal rules run locally before it.

For offline configuration provisioning, run `fastfence init --config-only --anonymization`. This writes configuration and private state without installing Laya or contacting Ollama. Run normal `init` when the prerequisites are available. `setup-laya` remains an advanced engine installation/repair command; it is not a separate quickstart step.

## Send a protected request

In another terminal, activate the same virtual environment from `fastfence-local`. This complete client reads your private agent credential without placing it in shell history:

```sh
source .venv/bin/activate
python - <<'PY'
import json
from pathlib import Path
import httpx

credentials = json.loads(Path("state/credentials.json").read_text())
with httpx.Client(timeout=120, trust_env=False) as client:
    response = client.post(
        "http://127.0.0.1:8000/api/models/complete",
        headers={"Authorization": "Bearer " + credentials["local-agent"]},
        json={"model": "qwen3:4b", "prompt": "Hello", "max_output_tokens": 256},
    )
    response.raise_for_status()
    print(response.json())
PY
```

Inspect `decision`, `reason`, `upstream_executed` and the semantic stage statuses. HTTP 200 alone does not mean allowed. Find the returned request ID in **Activity**. Interactive API schemas are at **http://127.0.0.1:8000/docs**.

## Download runnable examples

Download the [complete examples archive](downloads/fastfence-examples.zip) and extract it into `examples/` inside your installation directory. It contains executable Python files, the FastMCP policy and signatures, and five synthetic OCR fixtures under `documents/`; no credentials or private state.

```sh
curl -fL https://fastfence.dev/downloads/fastfence-examples.zip -o fastfence-examples.zip
python -m zipfile -e fastfence-examples.zip examples
python examples/protected_request.py --prompt 'Hello'
python examples/mcp_client.py --prompt 'Hello'
python examples/semantic_policy.py
```

The last command previews a named natural-language rule through your actual Laya assessor and displays a diff. It activates nothing unless you rerun with `--activate` after review. Each [example page](examples/protected-request.md) also includes the full source and a direct file download.

## Describe a rule, then test it through MCP

For semantic intent, follow the [named Laya rule example](examples/semantic-policy.md). For an exact restriction such as a forbidden letter, open **Policies → Add content rule**, choose **Word contains**, value `a`, **Input only**, **Models**, and case-insensitive matching. Preview `Hi` and `Cat`, review and activate.

Alternatively, **Describe a fast rule** asks Laya to draft this bounded deterministic configuration from your instruction. Inspect the generated operator, value and scope before activation; its local matcher differs from runtime semantic assessment.

```sh
python examples/mcp_client.py --prompt 'Cat'
python examples/mcp_client.py --prompt 'Hi'
```

`Cat` must be blocked before the protected model executes. `Hi` passes that rule and can reach Qwen if remaining policies permit it. Scope the rule to both directions if generated words should also be checked. Output denial cannot undo an upstream operation that already ran.

## Add document OCR

Run the packaged installer:

```sh
fastfence setup-ocr
fastfence doctor --full
```

Continue with [manual verification](manual-testing.md). OCR supports images and multipage PDFs and returns policy-checked Markdown. It does not edit document pixels. Restart after installing optional components, then run `fastfence doctor --full`.

## Update FastFence

Stop the gateway, activate its virtual environment and run:

```sh
python -m pip install --upgrade fastfence
fastfence doctor
fastfence serve
```

Reload the console after restart. Your working directory's `config/` and `state/` are separate from the installed package. Back them up and preserve them during upgrades. If a release updates pinned Laya helpers, follow that release's setup instructions; the installer refuses to overwrite modified helper files.

For policy-only updates, review and activate a higher version through **Policies**. Valid higher-version edits to `config/policy.yaml` also hot-reload. Invalid changes retain the last valid snapshot. `.env` changes require a restart.
