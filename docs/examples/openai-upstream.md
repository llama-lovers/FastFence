# Choose an OpenAI-compatible model upstream

FastFence can send protected business completions to native Ollama or to an
OpenAI-compatible Chat Completions server. The model ID in your request must be
allowed by your policy and available at the selected upstream.

Laya remains independent: security assessment still uses the local Ollama origin
in `FASTFENCE_OLLAMA_URL`. Choosing a different business provider does not disable
input or output inspection.

| Setting | Purpose |
| --- | --- |
| `FASTFENCE_MODEL_PROVIDER=ollama` | Default native Ollama business transport. |
| `FASTFENCE_MODEL_PROVIDER=openai` | Use the compatible `/chat/completions` transport. |
| `FASTFENCE_OPENAI_BASE_URL` | Upstream API base including `/v1`, such as `http://127.0.0.1:11434/v1`. |
| `FASTFENCE_OPENAI_API_KEY` | Optional upstream bearer credential, supplied only to the FastFence server. |
| `FASTFENCE_OLLAMA_URL` | Ollama origin for Laya and native Ollama, default `http://127.0.0.1:11434`. |

The upstream key is separate from the agent and management credentials used to
call FastFence. Keep it in the server's secret environment. Client requests cannot
choose a different upstream URL or supply an upstream credential. Remote bases
require HTTPS; HTTP is accepted only for loopback addresses. Inline URL credentials,
query strings, fragments, redirects and environment proxy settings are rejected
or disabled.

## Run against Ollama's compatible API

From the repository root, with `ollama serve` running in another terminal:

```sh
uv sync --locked
uv run fastfence init --anonymization
sh integrations/laya/setup.sh
ollama pull qwen3:4b
ollama pull qwen3:0.6b
FASTFENCE_MODEL_PROVIDER=openai \
FASTFENCE_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
uv run fastfence serve --port 8002
```

Ollama exposes its compatible Chat Completions route beneath `/v1`; its native
route remains available independently. See the
[Ollama compatibility documentation](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).

In a second terminal, run this complete protected smoke request. It reads a local
agent credential without printing it, requests a 256-token completion, and checks
the gateway verdict as well as upstream execution:

```sh
uv run python - <<'PY'
import json
import os
from pathlib import Path
import httpx

token = os.environ.get("FASTFENCE_AGENT_TOKEN")
if not token:
    path = Path("state/credentials.json")
    if not path.exists():
        path = Path("state/demo-tokens.json")
    credentials = json.loads(path.read_text())
    token = credentials.get("local-agent") or credentials["analyst-blue"]
with httpx.Client(timeout=120, trust_env=False) as client:
    response = client.post(
        "http://127.0.0.1:8002/api/models/complete",
        headers={"Authorization": "Bearer " + token},
        json={
            "model": "qwen3:0.6b",
            "prompt": "Say hello in one sentence.",
            "max_output_tokens": 256,
        },
    )
    response.raise_for_status()
    verdict = response.json()
print(json.dumps({key: verdict[key] for key in (
    "decision", "reason", "semantic_input_status", "semantic_output_status",
    "upstream_executed", "output",
)}, indent=2))
assert verdict["decision"] in {"allowed", "redacted"}, verdict["reason"]
assert verdict["upstream_executed"]
assert verdict["output"]["text"].strip()
PY
```

Use `FASTFENCE_MODEL_PROVIDER=ollama` to return to the native transport. The normal
REST, MCP and compatible client interfaces remain the same. Model classifications
can vary; an HTTP 200 alone does not mean that the gateway allowed a request.
Reasoning models can spend a short completion allowance entirely on reasoning,
returning empty text with `finish_reason: length`; adjust the allowed token budget
or the upstream model configuration if this occurs.

## Use vLLM

On a machine with vLLM installed and sufficient resources for the selected model,
start a compatible server with a stable model alias:

```sh
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --host 127.0.0.1 --port 8001 --served-model-name business-model
```

This uses vLLM's Chat Completions server; model and hardware prerequisites are
described in the [vLLM server documentation](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/).

In FastFence, add `business-model` to the model allowlist as described below, then
start the gateway:

```sh
FASTFENCE_MODEL_PROVIDER=openai \
FASTFENCE_OPENAI_BASE_URL=http://127.0.0.1:8001/v1 \
uv run fastfence serve --port 8002
```

For an authenticated server, configure its credential using vLLM's `--api-key`
option or `VLLM_API_KEY` environment variable, and inject the same value as
`FASTFENCE_OPENAI_API_KEY` in the gateway environment. For a remote deployment,
use your server's HTTPS API base instead of the loopback URL.

## Use llama.cpp

With `llama-server` installed and a compatible instruction-model GGUF file already
available, point `LLAMA_MODEL_PATH` at that file:

```sh
export LLAMA_MODEL_PATH=/absolute/path/to/your-instruct-model.gguf
llama-server --model "$LLAMA_MODEL_PATH" --alias business-model \
  --host 127.0.0.1 --port 8080
```

The alias becomes the API model ID. The server supports compatible Chat
Completions; see the [llama.cpp server reference](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Start FastFence with:

```sh
FASTFENCE_MODEL_PROVIDER=openai \
FASTFENCE_OPENAI_BASE_URL=http://127.0.0.1:8080/v1 \
uv run fastfence serve --port 8002
```

## Allow and call the served model

Connect a management identity in the console, open **Policies → Edit
configuration**, and add the model under `models` in Advanced configuration. For
the default initialized analyst/operator budgets, this entry permits both roles:

```yaml
business-model:
  roles: [analyst, operator]
  max_output_tokens: 256
  timeout_ms: 30000
  cost_microusd: 0
```

The advanced editor accepts the complete policy as JSON; this YAML fragment shows
the entry to add beneath `models`, rather than a standalone replacement policy.
Use roles with budgets in your actual installation. Review the complete change
and activate the next policy version. Then call the executable client:

```sh
uv run python -m examples.docs.protected_request \
  --url http://127.0.0.1:8002 --model business-model --prompt 'Hello'
```

The same allowlisted model is available through the
[compatible SDK client](openai-client.md) and [MCP client](mcp-client.md).

## Compatibility contract and verification

The adapter sends one nonstreaming text chat completion with `model`, `messages`,
`max_tokens`, `temperature: 0` and optional stop strings. Prompt-only calls become
one user message. The upstream must return one assistant text choice, an explicit
`stop` or `length` finish reason and nonnegative integer `prompt_tokens`,
`completion_tokens` and `total_tokens` with a consistent sum. Tool calls,
function calls, refusals, nontext content, missing or excessive usage, encoded or
oversized response bodies and invalid completion states fail closed. There are
no automatic provider retries.

Response JSON is limited to 262,144 bytes and text to 65,536 UTF-8 bytes; the
policy's smaller output bound still applies. The entire exchange uses the model
policy deadline. This interface does not implement provider tool execution,
streaming, multimodal messages or the Responses API.

The actual Ollama `/v1` path was checked with `qwen3:0.6b`: a 256-token request
returned nonempty text, explicit `stop` and 156 total provider token units. The
test suite also performs real loopback HTTP exchanges with synthetic replies and
adversarial transport fixtures. vLLM and llama.cpp commands were checked against
their official documentation; those engines were not run during this validation.

```sh
uv run pytest --no-cov -q \
  tests/unit/test_openai_upstream.py \
  tests/integration/test_openai_upstream_transport.py
```
