# Challenge readiness

FastFence implements all six formal requirement areas in the Goldman Sachs **AI Control Layer** brief within the supported model and tool paths. The latest recorded automated checkpoint passes **271 tests with 94.52% source coverage**. Actual Laya can draft a text rule from natural language; the gateway validates, previews and activates it, then enforces it locally without model calls for matching.

This page maps delivered behavior to evidence and identifies the remaining validation work. It replaces the obsolete pre-authoring numerical assessment. Requirement coverage is not a prediction of the jury score: robustness, performance and usability still depend on the scenarios evaluated.

## Formal requirements and delivered evidence

| Formal requirement | Delivered behavior | Evidence and current boundary |
| --- | --- | --- |
| Centralized policy engine | One validated policy/feed snapshot governs thresholds, block/redact actions, allowed tools/models and budgets. File and HTTP sources reload in the background; invalid updates retain the last valid configuration. | Automated reload, conflict, failure and immutable-snapshot tests. Actual authored-rule smoke demonstrates activation and removal without restart. Identity provisioning is separate startup configuration. |
| Hybrid deterministic and semantic controls | Authentication, roles, tenant boundaries, allowlists, privacy/redaction, 19 offline credential detectors, signatures and scoped text predicates; optional actual Ollama/Kev semantic assessment. | Positive/negative automated controls plus actual Qwen development probes: 20/20 on a small synthetic set. Kev has a tested integration contract but no delivered live benchmark. Broader semantic accuracy is unmeasured. The current Ollama assessor emits binary 0/1 scores: changing a threshold between 0 and 1 does not provide graduated sensitivity. |
| Budget and resource governance | Atomic reservation/settlement for calls, token units, estimated cost, runtime and concurrency. Model prompt-template overhead is reserved before execution. | Automated exhaustion, cancellation and concurrent-reservation tests. Limits are per instance/subject/day; token units and configured costs are estimates. Restart resets counters and separate instances do not share allowances. |
| Historical attack mitigation | A versioned external feed blocks literal markers for unsafe pickle/PyTorch loading, remote shell execution and instruction override. Policy/feed changes take effect dynamically. | Automated signature/feed tests and negative demo cases. Delivered coverage is bounded pattern detection: it does not inspect model binaries or establish protection against obfuscated or novel exploit variants. |
| Security reporting and auditing | Interactive dashboard shows controls, blocked decisions, budget use and configuration health. Sanitized decisions include request, policy/feed and execution metadata; management can export JSONL audit. | Automated dashboard, authorization and audit checks plus sanitized live reports. History is bounded in memory; restart and multiple instances limit retrospective visibility. |
| Automated self-testing | Executable offline positive, negative, redaction, budget, configuration, protocol and failure tests; separate actual-inference and performance runners. | Latest recorded checkpoint: 271 passed, 94.52% coverage. Live authored-rule report passes five HTTP enforcement cases. Unit/contract fixtures do not substitute for independent adversarial evaluation or transport load tests. |

Use the [testing guide](testing.md) for commands, report links, measured environments and exclusions. The detailed semantics and integration boundaries are documented in [policies](policies.md) and [integrations](integrations.md).

## Expected deliverables

| Deliverable | Current status |
| --- | --- |
| Integrable control layer | Implemented for REST, bounded OpenAI-compatible chat, authenticated MCP tool/resource access and actual Laya integration. Qwen completion uses REST/chat; the MCP adapter currently exposes business tools and memory. |
| Sample configuration | Deterministic and hybrid policy examples, threat feed, configurable privacy actions, thresholds and budgets, plus a generated settings reference. |
| Interactive dashboard | Implemented: identity connection, trial requests, policies, text-rule preview/activation, metrics, budgets, configuration health and audit export. Final integrated presentation rehearsal remains useful. |
| Executable test suite | Offline suite with an enforced coverage gate; reproducible live-model, Laya and local-performance runners. |
| Architecture diagram | Available in the [architecture guide](architecture.md). |

## Natural-language rules and local enforcement

Actual Laya/Qwen drafts a typed proposal from instructions such as “block words containing a.” The management API previews it; activation publishes the exact reviewed proposal without a second inference. Matching then uses local literal predicates. The delivered DSL supports `contains`, `word_contains` and `equals`, with input/output and model/tool scopes.

The [recorded authoring smoke](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/laya-authored-rules-live.json) passed five real HTTP enforcement cases: input denial, normalized Unicode denial, an allowed one-token Qwen completion, blocked model output and rule removal. Drafting took 3,635 ms; activation used zero inference; enforcement made zero semantic-assessor calls. A separate matching benchmark measured p95 0.075 ms for 64 rules over 4 KiB; this excludes transport and the rest of the gateway.

The Laya authoring feature is an additional product capability, not a separate mandatory item in the brief. It does not compile arbitrary RODO/GDPR requirements into guaranteed compliance. Unsupported instructions are rejected, and a model-generated proposal still needs review and representative examples.

## Remaining work for a stronger final submission

These are concrete improvements to evidence and presentation, not missing mandatory database products:

1. **Broader guardrail evaluation.** Extend the small development set with previously unseen paraphrases, indirect instructions, multilingual prompts and benign near-matches. Publish false positives and false negatives separately; keep model, prompt and policy versions with the results. Demonstrate the real effects of supported threshold changes; the current binary assessor does not establish calibrated sensitivity.
2. **Stronger exploit evidence.** Map each supported historical attack pattern to positive/negative fixtures and documented attack mechanics. Test whitespace, encoding and split-content variants; distinguish variants actually blocked from those outside the detector scope.
3. **Transport and sustained-load measurements.** Measure real HTTP/MCP latency, throughput, errors and concurrency with representative payloads and rule counts. Existing core and matcher benchmarks deliberately exclude transport; compare inference separately from enforcement overhead.
4. **A complete jury rehearsal.** Exercise the dashboard, actual Laya/Qwen, spontaneous rule changes, threshold changes, budget exhaustion, redaction and audit export together. Verify the exported request IDs explain each demonstrated decision. Existing reports cover individual flows, not a recorded full presentation rehearsal.
5. **Submission packaging.** Prepare and review the project description, demo instructions and final presentation against the separate competition rules. The rules require a PDF presentation of at most ten slides; this page is not that submission artifact.

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
