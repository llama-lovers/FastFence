# Getting started

## Install FastFence

Use macOS or Linux with [uv](https://docs.astral.sh/uv/getting-started/installation/). `uv tool run` downloads FastFence into its isolated tool cache; you do not need a source checkout or a manually activated virtual environment. The explicit Python selection matches FastFence's Python 3.12 requirement.

## Initialize and start with uv

Install [Ollama](https://ollama.com/) and start its service before initialization (`ollama serve` in another terminal, or the running desktop app). Keep Git and `sh` available for the pinned Laya engine.

```sh
mkdir fastfence-local
cd fastfence-local
uv tool run --python 3.12 fastfence@1.0.1 init
uv tool run --python 3.12 fastfence@1.0.1 doctor
uv tool run --python 3.12 fastfence@1.0.1 serve
```

Keep using this directory: `config/`, credentials and keys belong here, not in uv's tool cache. `uvx --python 3.12 fastfence@1.0.1` is the equivalent shorter prefix. The version pin makes repeated commands use the same release.

### Alternative: pip and a virtual environment

If you prefer the `fastfence` command directly, create a Python 3.12 environment in your working directory:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install fastfence uv
fastfence init
fastfence doctor
fastfence serve
```

Open **http://127.0.0.1:8000**. In **Connection**, enter the `local-agent` and `local-admin` tokens from your private `state/credentials.json`. Agent credentials send protected requests; management credentials review and change policies. Tokens stay in dashboard page memory.

Initialization creates `config/`, private credentials and the anonymization issuer keyring in your working directory. It also installs the pinned Laya engine and checks Ollama for the active policy's assessment model, downloading that model only when missing. Repeating `init` preserves valid existing credentials, policies and keys. Keep this directory when upgrading. Older installations with `state/demo-tokens.json` retain their `security-admin` and `analyst-blue` identities.

There are three separate roles:

- **Laya** is the Python engine that runs security assessments and helps draft rules. `init` installs it.
- **The assessment model** interprets the text being checked. The default is **Qwen3:4b**, served by Ollama. `init` checks and downloads the configured assessor.
- **Your application's model or tool** performs the requested work after input checks. The fresh policy also allows Qwen3:4b for completions, so the quickstart needs one model download. Choose another allowlisted model or an [OpenAI-compatible upstream](examples/openai-upstream.md) when your application needs it.

Assessment and completion are separate calls even when they use the same model. An agent that only calls tools or ACP peers does not need a separate completion model. Initialization preserves an existing model choice and does not download an extra business model. Missing assessment fails closed; precise literal rules run locally before it.

For offline configuration provisioning, run `uv tool run --python 3.12 fastfence@1.0.1 init --config-only` (or `fastfence init --config-only` in the pip environment). This writes configuration and private state without installing Laya or contacting Ollama. Run normal `init` when the prerequisites are available. `setup-laya` remains an advanced engine installation/repair command; it is not a separate quickstart step.

## Send a protected request

In another terminal, change to `fastfence-local`. This complete client uses an isolated Python environment containing HTTPX and reads your private credential without placing it in shell history:

```sh
uv run --no-project --python 3.12 --with httpx python - <<'PY'
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
uv run --no-project --python 3.12 python -m zipfile -e fastfence-examples.zip examples
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/protected_request.py --prompt 'Hello'
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/mcp_client.py --prompt 'Hello'
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/semantic_policy.py
```

For other example pages, replace their `python` prefix with `uv run --no-project --python 3.12 --with fastfence==1.0.1 python` when using the tool-based installation. Examples needing additional SDKs list those separately. Pip users can run examples with their activated environment.

The last command previews a named natural-language rule through your actual Laya assessor and displays a diff. It activates nothing unless you rerun with `--activate` after review. Each [example page](examples/protected-request.md) also includes the full source and a direct file download.

## Describe a rule, then test it through MCP

For semantic intent, follow the [named Laya rule example](examples/semantic-policy.md). For an exact restriction such as a forbidden letter, open **Policies → Add content rule**, choose **Word contains**, value `a`, **Input only**, **Models**, and case-insensitive matching. Preview `Hi` and `Cat`, review and activate.

Alternatively, **Describe a fast rule** asks Laya to draft this bounded deterministic configuration from your instruction. Inspect the generated operator, value and scope before activation; its local matcher differs from runtime semantic assessment.

```sh
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/mcp_client.py --prompt 'Cat'
uv run --no-project --python 3.12 --with fastfence==1.0.1 python examples/mcp_client.py --prompt 'Hi'
```

`Cat` must be blocked before the protected model executes. `Hi` passes that rule and can reach Qwen if remaining policies permit it. Scope the rule to both directions if generated words should also be checked. Output denial cannot undo an upstream operation that already ran.

## Add document OCR

Run the packaged installer:

```sh
uv tool run --python 3.12 fastfence@1.0.1 setup-ocr
uv tool run --python 3.12 fastfence@1.0.1 doctor --full
```

Continue with [manual verification](manual-testing.md). OCR supports images and multipage PDFs and returns policy-checked Markdown. It does not edit document pixels. Restart after installing optional components, then run `fastfence doctor --full`.

## Update FastFence

Stop the gateway. For the uv tool installation, explicitly select the newest published release:

```sh
uv tool run --python 3.12 fastfence@latest doctor
uv tool run --python 3.12 fastfence@latest serve
```

A plain unversioned tool command may reuse its cached version; `@latest` refreshes it. A pinned `@1.0.1` command remains pinned. [uv documents these cache semantics](https://docs.astral.sh/uv/concepts/tools/#tool-versions). A cached exact-version command can run with uv’s `--offline` option, but that only disables uv downloads: FastFence still needs its configured model service and normal initialization can download runtime components.

For pip, activate the existing virtual environment and run:

```sh
python -m pip install --upgrade fastfence
fastfence doctor
fastfence serve
```

Reload the console after restart. Your working directory's `config/` and `state/` are separate from the installed package. Back them up and preserve them during upgrades. If a release updates pinned Laya helpers, follow that release's setup instructions; the installer refuses to overwrite modified helper files.

For policy-only updates, review and activate a higher version through **Policies**. Valid higher-version edits to `config/policy.yaml` also hot-reload. Invalid changes retain the last valid snapshot. `.env` changes require a restart.
