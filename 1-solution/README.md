# 1. Solution

**FastFence changes security policy without changing agent code.** It sits
between applications or agents and their models, tools or ACP peers. Authenticated
REST, OpenAI-compatible and MCP interfaces share the same policy pipeline.
The ACP interface supports synchronous, stateless plain-text agent communication.

Start with the [10-slide presentation](../presentation/output/fastfence-submission.pdf)
and [recorded demonstration](../presentation/output/fastfence-submission.mp4).
Both describe public FastFence **1.0.7**. The film includes actual model calls,
MCP and ACP operations, document OCR and reversible token restoration. Individual
recordings use separate isolated configurations; the evidence identifies each scope.

## Why this is useful

- **Change enforcement while the agent keeps running.** The recorded `Hello`
  request first reaches the model. After a reviewed local rule change, the same
  request stops before upstream execution, without restarting the gateway.
- **Review policy meaning before activation.** Laya evaluates expected allowed
  and prohibited examples against active and proposed semantic policies.
  The dashboard shows results and a diff; successful review permits explicit
  activation and saves cases for later regression checks.
- **Keep useful document content while removing matched sensitive values.**
  Local OCR extracts a two-page PDF, privacy rules redact two synthetic email
  addresses, and the model receives protected Markdown.
- **Explain the execution boundary.** Decisions include a reason, policy/feed
  versions, request ID, queue wait and whether upstream work actually ran.

## Implemented controls

| Control | Implementation and scope |
| --- | --- |
| Identity and access | Verified bearer identities, agent/admin separation, tenant/role checks, model/tool allowlists. Browser-supplied roles cannot grant access. |
| Local text policies | Bounded literal operators, including exact matches and words containing a specified character. Input blocks precede upstream execution; output blocks suppress delivery. |
| Sensitive data | PII heuristics and offline `detect-secrets` detectors support blocking or redaction on input/output. Trusted custom Python detectors load at startup. |
| Threat signatures | Versioned signature feeds detect configured normalized strings and bounded token sequences, including representative exploit/instruction-override patterns. This is text inspection, not model-binary analysis. |
| Semantic assessment | Actual pinned Laya with configured Qwen evaluates text on applicable input/output stages. Named rules specify direction and target. Unavailable or malformed assessment fails closed. |
| Resource limits | Calls, token budget units, compute time, configured cost and concurrent execution limits. A bounded queue limits waiting count, bytes, time and requests per identity. |
| Privacy with context | Irreversible aliases or self-contained encrypted reversible tokens. Restoration is opt-in and policy-authorized; restored text passes output checks again. |
| Document input | Local OCR for images and multipage PDFs produces inspected Markdown for download or protected model completion. It does not edit PDF/image pixels. |
| Review and reporting | Policy diffs, reviewed test cases, manual request tools, security metrics and sanitized JSONL audit export. |

Implementation entry points: [execution engine](../src/fastfence/modules/control/application/services/engine.py),
[input inspection](../src/fastfence/modules/control/application/services/inspection.py),
[Laya adapter](../src/fastfence/modules/control/persistence/laya_semantic.py),
[secret detectors](../src/fastfence/modules/control/persistence/secrets.py),
[anonymization](../src/fastfence/modules/anonymization/),
[document workflow](../src/fastfence/workflows/document_markdown.py).

## One central policy, local enforcement

The installed runtime reads `config/policy.yaml` and `config/signatures.json`.
A configured HTTP provider can instead supply the authoritative policy/feed bundle.
Requests use an immutable validated snapshot, without a database lookup.
Valid higher-version updates activate without restart. Invalid updates retain the
last valid snapshot; queued requests recheck the current policy before execution.
`.env` contains startup settings and requires a restart when changed.

Use complete, tracked configurations rather than assembling unvalidated fragments:

| Complete configuration | Purpose |
| --- | --- |
| [Packaged policy](../src/fastfence/shared/defaults/policy.yaml) and [feed](../src/fastfence/shared/defaults/signatures.json) | Fresh installation with actual Laya assessment. |
| [FastMCP policy](../examples/docs/policy.yaml) and [feed](../examples/docs/signatures.json) | Actual local uppercase tool with deterministic controls; explicitly disables semantic inference for this example. |
| [ACP policy](../examples/docs/acp_policy.yaml) | Allowlisted peer-agent example with deterministic controls. |

The [policy guide](../docs/policies.md) describes every supported field and the
[settings reference](../docs/settings.md) covers local/HTTP providers and deployment
settings. [Configuration provider tests](../tests/unit/test_config_providers.py)
exercise last-valid retention and coherent snapshot publication.

## Laya has two separate roles

**Describe a fast rule** uses Laya during management to propose a bounded policy
change, such as a literal text rule, selective email redaction or narrower tool
permissions. The operator reviews examples and the diff. Activation publishes
the stored candidate; the resulting literal matcher runs locally. This does not
execute generated Python or compile arbitrary prose into unrestricted regex.

**Add Laya rule** stores a natural-language instruction that the actual semantic
assessor evaluates at request time. The named-rule workflow compares active and
proposed behavior, replays saved relevant cases and requires a valid review receipt
for activation. Cases are stored privately in `config/semantic-policy-tests.yaml`.
The separate fast-rule authoring workflow uses `config/policy-tests.yaml`.
See the [complete semantic example](../examples/docs/semantic_policy.py) and
[review guide](../docs/examples/semantic-policy.md).

These two paths have different costs and guarantees. Use local text rules for exact
characters or words. Semantic judgments can be wrong; passing reviewed examples
establishes those cases, not general accuracy or legal compliance.

## Recorded proof and operating boundaries

| Evidence | What it establishes |
| --- | --- |
| [Policy recording](../presentation/output/demo-evidence.json) | Real model response, local hot reload and eight-case Laya review. The financial negative was already blocked by the base assessment. |
| [OpenAI SDK](../presentation/output/integration-demo-evidence.json) | Actual SDK/model request allowed, then the same call blocked before upstream after policy activation. |
| [MCP](../presentation/output/mcp-demo-evidence.json) / [ACP](../presentation/output/acp-demo-evidence.json) | Actual protocol clients and local operations; invocation counters stay unchanged after input denial. No LLM inference in these protocol tests. |
| [Reversible privacy](../presentation/output/anonymization-demo-evidence.json) | Actual RSA/AES token protection and restoration toggle through a deterministic echo tool; gateway holds both recipient keys. |
| [OCR](../presentation/output/ocr-demo-evidence.json) | Two-page extraction, two email redactions and actual protected Qwen completion. |
| [Queue](../evaluation/results/request-queue-1.0.7.json) | 1,000 controlled requests and a separate 12-request real-model run; these are different test scopes. |

Budgets, audit retention and admission queues belong to one process and reset on
restart. There is no shared multi-instance budget coordinator or business-request
deduplication guarantee. A blocked output cannot undo an upstream operation that
already ran. Reversible tokens avoid a conversation mapping database, but require
intact tokens, matching keys and policy permission. The semantic limitation and
measured performance scopes remain visible in the linked evidence.
