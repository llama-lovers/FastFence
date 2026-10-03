# Challenge readiness

This is our assessment of FastFence against the Goldman Sachs **AI Control Layer** challenge document supplied for HackYeah 2026. The source is the locally provided `CRIETRIA AI Control Layer.pdf`; the participant document is not republished here. Its formal requirements are on page 3 and evaluation approach and weights on page 4.

The scores below are our readiness estimates, not jury scores or a security certification. The weighted **6.7/10** estimate below records the earlier pre-authoring checkpoint. The subsequent bounded Laya authoring implementation is described below; these historical scores have not been regraded and are not a claim that the newer version is complete.

## Weighted evaluation categories

| Category | Challenge weight | Our estimate | Evidence and remaining work |
| --- | --- | --- | --- |
| Robustness and guardrail quality | 30% | 6/10 | Real auth, role/tenant checks, signatures, offline secret detectors, privacy decisions, and fail-closed errors. Semantic detection remains model-dependent; literal signatures are bypassable by transformations outside their scope. |
| Architecture and performance efficiency | 20% | 8/10 | Typed layered core, immutable snapshots, memory-only accounting, no deterministic request-time configuration I/O, and a reproducible operational benchmark. Current allowed-call p95 is 0.142 ms with a zero-wait fixture; HTTP and LLM time are excluded. |
| Security reporting | 20% | 6/10 | Dashboard, resource counters, configuration health, bounded sanitized audit, and JSONL export. Durable history, SIEM integration, alerting, and richer threat analysis are not implemented. |
| Self-testing completeness | 15% | 8/10 | 174 automated tests with 93.96% source coverage, positive/negative controls, source failures, concurrency, protocol contracts, plus separate real-model and real-Laya reports. Wider independent adversarial evaluation remains necessary. |
| Practical implementability and scalability | 15% | 6/10 | Runnable local setup, centralized file/HTTP configuration, REST/OpenAI-compatible/MCP adapters, and real Laya integration. Business tools are simulated; multi-instance spending coordination and production rollout remain unfinished. |

The calculation is `6 × 0.30 + 8 × 0.20 + 6 × 0.20 + 8 × 0.15 + 6 × 0.15 = 6.7`.

## Formal requirements, point by point

| Requirement | Our estimate | Delivered | Gap |
| --- | --- | --- | --- |
| Centralized policy engine | 8/10 | Validated policy/feed, role and model allowlists, block/redact settings, budgets, thresholds, background file/HTTP reload, coherent snapshots, and last-valid retention. | Rule authoring is limited to the supported literal DSL; arbitrary semantic/compliance policy compilation is absent. Identity provisioning is separate startup configuration. |
| Deterministic controls | 8/10 | Auth, role and tenant access, target allowlists, bounded payloads, literal attack signatures, privacy heuristics, and 19 offline detect-secrets format/keyword detectors. | Heuristics do not recognize every secret, PII type, encoding, or exploit. Fragments across separate fields/messages are not reconstructed. |
| Semantic controls | 6/10 | Actual optional Ollama/Kev assessment, bounded requests, input/output scans, configured threshold, and fail-closed provider errors. Recorded Qwen binary-schema development probes pass 20/20. | Small development probes do not establish general accuracy. Kev has an adapter but is not benchmarked in the delivered evidence. |
| Budget and resource governance | 7/10 | Atomic reservations and settlement for calls, conservative token units, estimated cost, runtime, and concurrency, scoped to instance/subject/UTC day. | Counters reset on restart; instances do not share allowances. Token units and configured tariffs are estimates, not provider invoice reconciliation. |
| Historical attack mitigation | 4/10 | Versioned external feed with representative pickle, unsafe PyTorch loading, remote-shell, and instruction-override markers. | Literal pattern detection does not prevent all deserialization, code execution, supply-chain, encoded, or novel attacks. |
| Security reporting and auditing | 6/10 | Real-time dashboard metrics, local budget usage, configuration diagnostics, bounded sanitized records, and management-only JSONL export. | No durable audit store, SIEM connector, alerting system, or cross-instance aggregation. |
| Automated self-testing | 8/10 | Positive/negative guardrails, budgets, concurrent races, live configuration, source outages, authenticated HTTP/MCP, detector failures, and real inference checks recorded separately. | External adversarial testing, longer stability runs, and production transport/load validation remain outside current evidence. |

## Expected deliverables

| Deliverable | Current status |
| --- | --- |
| Integrable control layer | Delivered for the supported REST, OpenAI-compatible chat, MCP tool/resource, and Laya paths. It is not an arbitrary upstream proxy. |
| Sample configuration | Delivered: deterministic and hybrid policies, signature feed, settings reference, and configurable privacy/budget behavior. |
| Interactive dashboard | Delivered: identities, trial invocations, policy editing, metrics, budgets, source health, and audit export. |
| Executable test suite | Delivered with a coverage gate and separate live-model/performance evidence. |
| Architecture diagram | Available in the [architecture guide](architecture.md). |

## Natural-language rule authoring

The earlier **0/10 (planned)** status has been superseded by a bounded implementation: actual Laya drafts a typed text rule, the management API validates and previews it, and an exact reviewed proposal can be activated without another model call. The challenge PDF does not explicitly require that feature, detect-secrets, or Laya. It does require hybrid controls, configurable governance, testing, and reporting; judges may modify configuration and try spontaneous prompts.

The authoring CLI supports instructions such as “reject words containing a” through dedicated text rules with input/output and model/tool scope. Runtime matching is local. A single-letter legacy attack signature still fails its separate minimum-length validation; the new text-rule mechanism handles that use case. MCP currently invokes business tools and memory; Qwen completion uses REST or OpenAI-compatible chat. These boundaries matter when preparing an interactive demonstration.

## What to demonstrate

Show an allowed request, deterministic denial before upstream execution, output redaction, role and tenant denial, budget exhaustion, and an invalid configuration update retaining the last valid snapshot. Then demonstrate an actual local model through the protected path and explain the difference between model inference latency and deterministic control overhead.

Use the [quickstart](getting-started.md), [policies](policies.md), [integrations](integrations.md), and [testing evidence](testing.md) for reproducible steps. Every demonstration should distinguish actual controls and inference from simulated business data.
