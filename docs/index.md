![FastFence logo](assets/fastfence-logo.svg){ .fastfence-landing-logo width="120" height="121" }

# FastFence

**Security policies for agents. Local enforcement for every call.**

FastFence checks AI requests and responses against your access, privacy, text and resource policies. Connect through REST, an OpenAI-compatible endpoint, MCP or a configured ACP peer. Describe a rule with Laya, review its changes and tests, then activate it without restarting the gateway.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Follow a tutorial](learn.md){ .md-button }
[HTTP API reference](reference/http-api.md){ .md-button }

## Start locally

Use Python 3.12 and a running [Ollama](https://ollama.com/) service. Install the package into a virtual environment in your own working directory:

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

`init` prepares private configuration, installs Laya and downloads the configured assessor if needed. The fresh default uses Qwen3:4b for both assessment and completion in separate calls; no second model is required. Open **http://127.0.0.1:8000** and connect with your generated local credentials. The [installation guide](getting-started.md) covers prerequisites and private configuration. No FastFence source checkout is required.

## Choose your task

| I want to… | Start here |
| --- | --- |
| Run a protected model request | [Learn: your first request](learn.md#1-send-a-protected-model-request) |
| Describe a rule and understand how it changes behavior | [Policies and review](policies.md) |
| Connect an existing agent or MCP client | [Integration contract](integration-reference.md) |
| Connect a peer agent through ACP | [ACP agent-to-agent example](examples/acp.md) |
| Configure privacy, anonymization or budgets | [Policy configuration](policies.md) |
| Find an endpoint or request schema | [Source-backed HTTP reference](reference/http-api.md) |
| Configure a local installation | [Environment settings](settings.md) |
| Verify the system myself | [Manual verification](manual-testing.md) |
| Run framework integration code | [Executable examples](examples/fastmcp-server.md) · [OpenAI SDK](examples/openai-client.md) |
| Give an LLM the documentation | [llms.txt](llms.txt) · [llms-full.txt](llms-full.txt) |

## How it works

An authenticated request passes through access checks, input controls and budget reservation before the upstream operation runs. FastFence then checks the response and records a sanitized decision. Fast deterministic checks run locally. The default product configuration also uses Laya for semantic input and output inspection of content that reaches that stage; unavailable analysis fails closed.

Laya has two separate roles. On the management path it drafts bounded rules that become fast local checks after review. On the runtime path it assesses content against security guidance and your natural-language semantic policy. Compiled text matching itself needs no model call, while enabled semantic inspection does.

Policies can reload from local files or a trusted HTTP configuration source. Invalid updates keep the last valid configuration. A proposed change is separate from an active policy: inspect the diff, verify expectations and explicitly publish it.

## Runtime boundaries

The local product starts without simulated business tools. Runnable business-tool examples are separate from the default runtime. Model execution requires an allowlisted model on the configured Ollama or OpenAI-compatible upstream. OCR converts supported documents into policy-checked Markdown; it does not edit images or PDFs.

Budgets and bounded audit logs are process-local and reset on restart. Reversible anonymization uses authenticated tokens and local keys, with explicit permission to restore originals. An output denial cannot undo an upstream operation that has already run. See [architecture](architecture.md) for the trust and deployment boundaries.

FastFence is Apache-2.0 licensed.
