# OpenAI Python SDK through FastFence

This client sends text chat to FastFence's `/v1/chat/completions`. FastFence applies its policy before calling the configured model provider. The client credential is a **FastFence agent token**, not your upstream provider key.

## Run with Ollama

Follow [installation](../getting-started.md), start Ollama, pull `qwen3:4b` for Laya and `qwen3:0.6b` for completion, then run `uv run fastfence serve`. Set `FASTFENCE_AGENT_TOKEN` to your provisioned agent credential.

```sh
uv run --with openai python examples/docs/openai_client.py 'Hi'
```

The script prints the protected model response. Set `FASTFENCE_MODEL` if your allowlisted model differs. Set `FASTFENCE_URL` if the gateway listens elsewhere; this remains the gateway URL, never the upstream URL.

## Complete client

<!-- source: examples/docs/openai_client.py -->

## Verify blocking

In **Policies**, add a model-input literal rule for `forbidden`, test and activate it. Then run:

```sh
uv run --with openai python examples/docs/openai_client.py 'forbidden'
```

Expected: nonzero exit and an HTTP denial. **Activity** shows the input rule and `upstream_executed: false`. The client disables automatic retries and never falls back to a direct provider.

## Use a different model backend

Keep this client unchanged and follow [OpenAI-compatible upstream configuration](openai-upstream.md) on the gateway. The gateway's provider key remains server-side. Laya's semantic model is configured separately.

Supported here: non-streaming, text-only chat at temperature zero. Streaming, tool-call generation and multimodal messages are not implemented by this compatibility adapter. Use [REST](protected-request.md) if you need the complete security verdict in the response.
