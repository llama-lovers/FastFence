# Challenge readiness

FastFence implements all six formal requirement areas in the Goldman Sachs **AI Control Layer** brief within the supported model and tool paths. The latest verified integration checkpoint and its coverage are recorded in the [testing guide](testing.md). Actual Laya drafts text restrictions, selective privacy controls and tool-role restrictions in the dashboard; the gateway previews and activates the exact reviewed candidate, then enforces it locally without authoring-model calls.

This page maps delivered behavior to evidence and identifies the remaining validation work. It replaces the obsolete pre-authoring numerical assessment. Requirement coverage is not a prediction of the jury score: robustness, performance and usability still depend on the scenarios evaluated.

## Formal requirements and delivered evidence

| Formal requirement | Delivered behavior | Evidence and current boundary |
| --- | --- | --- |
| Centralized policy engine | One validated policy/feed snapshot governs thresholds, block/redact actions, allowed tools/models and budgets. File and HTTP sources reload in the background; invalid updates retain the last valid configuration. | Automated reload, conflict, failure and immutable-snapshot tests. Actual authored-rule smoke demonstrates activation and removal without restart. Identity provisioning is separate startup configuration. |
| Hybrid deterministic and semantic controls | Deterministic auth, roles, tenant boundaries, allowlists, privacy, 19 offline credential detectors, normalized signatures and scoped text predicates; actual Ollama/Kev assessment when enabled. | Frozen 60-case PL/EN severity holdout: all 20 clearly malicious cases detected, 46 exact categories, errors retained. Six actual-model HTTP cases prove threshold 0.5 versus 0.8 changes suspicious decisions. Scores are ordinal, not probabilities; ambiguous content remains a weakness. |
| Budget and resource governance | Atomic reservation/settlement for calls, token units, estimated cost, runtime and concurrency. Model prompt-template overhead is reserved before execution. | Automated exhaustion, cancellation and concurrent-reservation tests. Limits are per instance/subject/day; token units and configured costs are estimates. Restart resets counters and separate instances do not share allowances. |
| Historical attack mitigation | Versioned feed, bounded Unicode/whitespace normalization, one-layer textual percent/base64 views, adjacent list-fragment reconstruction and configured token sequences. | The same 38-case inert corpus improved from 10 to 30 detected attack variants; all 30 target variants now match, with six true negatives and two conservative quoted-marker false positives. This is text inspection, not executable CVE reproduction or universal exploit prevention. |
| Security reporting and auditing | Interactive dashboard shows controls, blocked decisions, budget use and configuration health. Sanitized decisions include request, policy/feed and execution metadata; management can export JSONL audit. | Automated dashboard, authorization and audit checks plus sanitized live reports. History is bounded in memory; restart and multiple instances limit retrospective visibility. |
| Automated self-testing | Executable offline positive, negative, redaction, budget, configuration, protocol and failure tests; separate actual-inference and performance runners. | Offline suite, actual-model threshold evidence, real Laya operation probes, browser authoring and actual MCP completion are recorded separately. A 76-group real HTTP/MCP transport matrix verifies outcomes, budgets and audit. Development corpora do not establish universal detection quality. |

Use the [testing guide](testing.md) for commands, report links, measured environments and exclusions. The detailed semantics and integration boundaries are documented in [policies](policies.md) and [integrations](integrations.md).

## Expected deliverables

| Deliverable | Current status |
| --- | --- |
| Integrable control layer | Implemented for REST, bounded OpenAI-compatible chat, authenticated MCP tool/resource access and actual Laya integration. Qwen completion is available through REST/chat and the authenticated MCP complete tool; business tools and tenant memory use the same core. |
| Sample configuration | Deterministic and hybrid policy examples, threat feed, configurable privacy actions, thresholds and budgets, plus a generated settings reference. |
| Interactive dashboard | Implemented: identity connection, trial requests, policies, text-rule preview/activation, metrics, budgets, configuration health and audit export. Real Chromium walkthrough validates natural-language drafting, preview, activation, input denial and visible audit; a real MCP Qwen completion is checked in the same isolated gateway. |
| Executable test suite | Offline suite with an enforced coverage gate; reproducible live-model, Laya and local-performance runners. |
| Architecture diagram | Available in the [architecture guide](architecture.md). |

## Natural-language rules and local enforcement

Actual Laya/Qwen drafts a typed proposal from instructions such as “block words containing a.” The management API previews it; activation publishes the exact reviewed proposal without a second inference. Matching then uses local literal predicates. The text DSL supports `contains`, `word_contains` and `equals`, with input/output and model/tool scopes. Additional bounded operations select privacy actions for all detectors or email/Polish-ID detectors, and narrow existing tool-role permissions. Proposals are management-identity bound, expire, and cannot overwrite an unreviewed concurrent source change.

The [recorded authoring smoke](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/laya-authored-rules-live.json) passed five real HTTP enforcement cases: input denial, normalized Unicode denial, an allowed one-token Qwen completion, blocked model output and rule removal. Drafting took 3,635 ms; activation used zero inference; enforcement made zero semantic-assessor calls. A separate matching benchmark measured p95 0.075 ms for 64 rules over 4 KiB; this excludes transport and the rest of the gateway.

The Laya authoring feature is an additional product capability, not a separate mandatory item in the brief. It does not compile arbitrary RODO/GDPR requirements into guaranteed compliance. Unsupported instructions are rejected, and a model-generated proposal still needs review and representative examples.

## Validation delivered and remaining limitations

- **Broader guardrail evaluation:** 60 newly labeled holdout cases, separate from development, with complete confusion and per-threshold FP/FN reports. The corpus is self-authored; ambiguous intent still needs improvement and independent evaluation.
- **Historical variants:** before/after evidence for whitespace, Unicode, encoded and split-list variants, plus limits and near-match regressions. Quoted dangerous strings remain conservatively blocked and deeper/novel transforms remain outside scope.
- **Actual transport:** 76 HTTP/MCP groups with 0/1/64 rules, short/8 KiB payloads and concurrency 1/8. All 7,680 business invocations, budgets and audit entries reconciled. The worst measured p95 was about 131 ms with a simulated 15 ms backend; this motivates further profiling, not a blanket sub-millisecond gateway claim.
- **Interactive product:** actual Laya drafts and activates through the dashboard; selective email redaction preserves other privacy blocking, role restriction rejects the removed role, and model calls work through HTTP/MCP. The exact changes are reviewed because model proposals can misinterpret instructions; initial failures are retained.
- **Further operational work:** longer-duration soak testing, broader workloads, independent adversarial review and complete deployment-specific demonstrations remain useful beyond these bounded development checks.

Durable audit storage, SIEM connectors, provider-invoice reconciliation and coordinated global quotas are possible production extensions. The brief does not prescribe those specific implementations as separate deliverables. Their absence still defines operational limits that matter when discussing long-running or multi-instance deployments. Simulated business data is explicitly labeled; actual model and Laya calls are demonstrated separately.

## Evaluation weights in the supplied documents

The supplied documents differ in the last two weights. Both are recorded here without assuming which version the organizers will apply:

| Category | Criteria brief, page 4 | Competition rules, section 11 |
| --- | --- | --- |
| Robustness and guardrail quality | 30% | 30% |
| Architecture and performance efficiency | 20% | 20% |
| Security reporting | 20% | 20% |
| Self-testing completeness | 15% | 20% |
| Practical implementability and scalability | 15% | 10% |

Sources: the locally supplied `CRIETRIA AI Control Layer.pdf` (formal requirements, page 3; validation and weights, page 4) and `RULES AI Control Layer.pdf` (submission requirements, section 5; weights, section 11). Participant documents are not republished here.

For the demonstration, start with the [quickstart](getting-started.md), then follow the [rule-authoring steps](policies.md#draft-a-rule-in-natural-language-with-laya). The strongest claim is the behavior a judge can reproduce from the supplied configuration, commands and reports.
