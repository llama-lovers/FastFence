# Real Laya behind FastFence

This integration runs the actual upstream [`aayushch/laya`](https://github.com/aayushch/laya) Python engine at revision `b3b998c03dc44076675305581eb4640b9bf6ff8f`. Laya is Copyright 2026 Aayush Chawla, Apache-2.0; the checkout retains its original license and notices. No upstream implementation is copied into FastFence, and the unrelated `laya` PyPI package is never installed.

From the FastFence repository root:

```sh
integrations/laya/setup.sh
# Start FastFence with a valid model-enabled policy and initialized credentials.
# See the main README for the hybrid policy and Ollama setup.
integrations/laya/run-demo.sh
```

Setup pins the source revision and installs its hash-verified `engine/requirements.lock` into `state/laya/venv`. The source lives in `state/laya/upstream`; both are gitignored local state. Python 3.12, Git, uv, the running gateway, and the allowed Ollama model are required. The Rust desktop UI is unnecessary for this backend demonstration.

The demo calls real `laya.llm.client.llm_call`, which uses LiteLLM and FastFence's `/v1/chat/completions` endpoint. It also registers a `fastfence_invoke` handler in Laya's actual `_TOOL_HANDLERS` registry and dispatches it through `laya.llm.tools.executor.execute_tool` to FastFence's `/api/invoke`. The five scenarios cover a real model response, blocked model injection, allowed business search, a denied payment preparation, and denied access to another tenant's resource. The business handlers return the gateway's synthetic demo data; no real payment or external connector runs.

Every model and tool request in this demo crosses FastFence independently. A production Laya deployment must route each relevant native business handler through the gateway too; registering one guarded handler does not intercept every native Laya connector automatically. Network egress restrictions are needed to prevent an agent reaching providers directly.

The runner creates temporary Laya configuration and SQLite audit storage, replacing only its process-local keychain lookup with the trusted demo token. It does not change `~/.laya`, the OS keychain, or connect Gmail/Slack/n8n accounts. Tokens are read from the gateway's private `state/demo-tokens.json` and are never exported. `--url`, `--model`, `--credentials`, `--source`, and `--output` can override local paths and endpoints.

The compatibility surface supports bounded text messages with system/user/assistant labels, deterministic temperature zero, non-streaming responses, one completion, and bounded stop sequences. Laya's default 65,536-token request is accepted and clamped first to FastFence's hard ceiling of 2,048 and then to the active policy's per-model limit. Streaming, generated tool calls, structured output, multimodal content, unknown options, and invalid requests fail closed. Actual business tools use `/api/invoke` separately.

Completion responses expose `usage: null`: conservative budget units include safety scans and cannot serve as a provider billing split. Gateway request/policy/feed/decision metadata is available through headers and the `fastfence` response object.

The sanitized live report is written to `results/live.json`. It contains case results, latency, request IDs, execution flags, and gateway audit metadata; it excludes prompts, generated text, credential values, and request/response bodies. A successful run exits zero only when all five results match and all five audit records are present, including denial before upstream execution.

## Natural-language rule authoring

`author-rule.sh` uses actual Laya inference to draft a bounded rule through a trusted loopback Ollama server. Start FastFence and Ollama with `qwen3:4b` available, then:

```sh
integrations/laya/author-rule.sh \
  --instruction 'Blokuj każde słowo zawierające literę a.' \
  --sample Hello --sample Cat --save-proposal state/no-letter-a.json
cat state/no-letter-a.json
integrations/laya/author-rule.sh \
  --proposal state/no-letter-a.json --sample Hello --sample Cat --activate
```

Drafting defaults to `--direction both --target model` and does not publish a policy. Activation reuses the exact reviewed proposal, invokes no model, merges into the current policy and preserves version-conflict protection. `--direction` accepts input/output/both; `--target` accepts model/tool/all. `--output` writes sanitized metadata; `--save-proposal` writes the actual private rule with mode0600. Both endpoint overrides accept loopback origins only.

The rule DSL supports literal contains, word_contains and equals with block action. Invalid or unsupported proposals fail closed; this is not an arbitrary-code or general-compliance generator. Review the exact literal and preview representative samples because model interpretations can be wrong.

Unlike the protected agent demo, the authoring model is a management-plane dependency reached directly through trusted local Ollama. The runner isolates Laya configuration/database and adapts only local credential lookup and structured-output call options for Ollama. Policy activation remains authenticated with the management identity. The compiled rule requires no Laya/model calls during enforcement.

See [rule semantics and APIs](../../docs/policies.md#draft-a-rule-in-natural-language-with-laya).
