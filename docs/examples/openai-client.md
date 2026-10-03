# OpenAI Python SDK through FastFence

This client sends text chat to FastFence's `/v1/chat/completions`. FastFence applies its policy before calling the configured model provider. The client credential is a **FastFence agent token**, not your upstream provider key.

Download the [complete examples](../downloads/fastfence-examples.zip) into your installation's `examples/` directory. Run commands from the installation directory; `uv run` supplies Python 3.12 and the FastFence package for each example, without activating a virtual environment.

## Run with Ollama

Follow [installation](../getting-started.md): start Ollama, run `uv tool run --python 3.12 fastfence@1.0.1 init --anonymization`, then `uv tool run --python 3.12 fastfence@1.0.1 serve`. Initialization installs Laya and prepares the default Qwen3:4b model. Set `FASTFENCE_AGENT_TOKEN` to your provisioned agent credential.

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 --with openai==2.21.0 python examples/openai_client.py 'Hi'
```

The script prints the protected model response. Set `FASTFENCE_MODEL` if your allowlisted model differs. Set `FASTFENCE_URL` if the gateway listens elsewhere; this remains the gateway URL, never the upstream URL.

## Complete client

<!-- source: examples/docs/openai_client.py -->

## Verify blocking

In **Policies**, add a model-input literal rule for `forbidden`, test and activate it. Then run:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 --with openai==2.21.0 python examples/openai_client.py 'forbidden'
```

Expected: nonzero exit and an HTTP denial. **Activity** shows the input rule and `upstream_executed: false`. The client disables automatic retries and never falls back to a direct provider.

## Use a different model backend

Keep this client unchanged and follow [OpenAI-compatible upstream configuration](openai-upstream.md) on the gateway. The gateway's provider key remains server-side. Laya's semantic model is configured separately.

Supported here: non-streaming, text-only chat at temperature zero. Streaming, tool-call generation and multimodal messages are not implemented by this compatibility adapter. Use [REST](protected-request.md) if you need the complete security verdict in the response.
