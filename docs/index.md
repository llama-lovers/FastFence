# FastFence

**Fast agents. Clear boundaries.**

FastFence is an AI Control Layer built for the Goldman Sachs challenge at HackYeah 2026. Place it between an agent and its business tools, tenant memory, or allowlisted local model. Each invocation verifies identity, applies policy, reserves a budget, inspects the upstream result, and records a sanitized decision.

Start with the [quickstart](getting-started.md), then choose an [integration](integrations.md) and configure your [policies](policies.md).

## What works today

| Capability | Delivered behavior |
| --- | --- |
| Authentication and permissions | Provisioned bearer identities, role allowlists, separate management access, and tenant-scoped memory. |
| Deterministic guardrails | Authored text restrictions, versioned literal attack signatures, privacy heuristics, and offline detect-secrets credential detectors. |
| Hybrid checks | Optional real Ollama or Kev semantic analysis; configured provider failures fail closed. |
| Resource limits | Atomic process-local budgets for calls, conservative token units, estimated cost, runtime, and concurrency. |
| Central configuration | Local files or a trusted HTTP bundle, background reload, immutable snapshots, and last-valid retention. |
| Reporting | Interactive dashboard, bounded sanitized audit, JSONL export, decision counts, resource usage, and configuration health. |
| Integration | REST, bounded OpenAI-compatible chat, authenticated MCP tools/resources, and a real Laya demonstration. |

The default policy uses deterministic checks and needs no running model. The business handlers return simulated data; they do not execute real payments or connect external accounts. Protected model completion and hybrid checks use an actual separately hosted model when configured.

## Current boundaries

The MCP server exposes controlled business-tool invocation and tenant memory. Qwen completion uses REST or the OpenAI-compatible endpoint; a model-completion MCP tool is not implemented.

The [Laya authoring CLI](policies.md#draft-a-rule-in-natural-language-with-laya) drafts bounded text rules from natural language. Validate and preview the proposal, review its exact private JSON, then activate that same proposal without another model call. Runtime matching is local. The supported DSL covers literal text restrictions; broader semantic or compliance instructions are outside its scope.

Budgets and audit live in memory and reset on restart. Independent instances have independent allowances; there is no global spending coordinator. A blocked output cannot undo upstream actions that already ran.

Read the [architecture](architecture.md), [validation evidence](testing.md), [challenge readiness assessment](challenge-readiness.md), and [deployment guidance](deployment.md) before extending the demo.

## Open source

FastFence is licensed under Apache-2.0. Source, license notices, specifications, and reproducible reports are available in the [project repository](https://github.com/llama-lovers/HackYeah2026-challenge-second). Third-party integrations retain their own licenses and notices.

The repository currently remains private: source and report links require repository access. Publishing this documentation does not make the source repository public.
