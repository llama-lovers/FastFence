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

Install and start [Ollama](https://ollama.com/). The Laya installer also needs Git and `sh` on your machine to fetch its pinned external engine; it does not require cloning FastFence.

```sh
fastfence init --anonymization
fastfence setup-laya
ollama pull qwen3:4b
ollama pull qwen3:0.6b
fastfence doctor
fastfence serve
```

Open **http://127.0.0.1:8000**. In **Connection**, enter the `local-agent` and `local-admin` tokens from your private `state/credentials.json`. Agent credentials send protected requests; management credentials review and change policies. Tokens stay in dashboard page memory.

Initialization creates `config/`, private credentials and the optional anonymization issuer keyring in your working directory. Repeating `init --anonymization` preserves valid existing credentials, policies and keys. Keep this directory when upgrading. Older installations with `state/demo-tokens.json` retain their `security-admin` and `analyst-blue` identities.

The default policy uses **Laya/Qwen3:4b for input and output assessment** and **Qwen3:0.6b for the protected completion**. These are separate model calls. Missing assessment fails closed. Precise literal rules run locally before model assessment.

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
        json={"model": "qwen3:0.6b", "prompt": "Hello", "max_output_tokens": 128},
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

For application development and repository test commands, see [Contributing](contributing.md).
