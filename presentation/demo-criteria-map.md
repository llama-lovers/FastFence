# FastFence demo: official criteria and evidence map

This is a factual production guide for the next film, not a jury score or a new
benchmark. Existing recordings show public PyPI FastFence 1.0.7. The OpenAI client integration also has verified actual outcomes. Its code and
results are rendered from the real execution transcript, not a live terminal
screen capture. Test-suite results remain separately scoped evidence.

## Official sources and the weighting discrepancy

Read in full, with the scoring pages also visually inspected:

- `HackYeah 2026 - Rules for Participants/Partner Task [Goldman Sachs] - AI Control Layer/CRIETRIA AI Control Layer.pdf`, page 4, sections 6–8.
- `HackYeah 2026 - Rules for Participants/Partner Task [Goldman Sachs] - AI Control Layer/RULES AI Control Layer.pdf`, page 2, clause 11. The directory is a sibling of the canonical repository.

| Criterion | CRIETRIA, section 8 | RULES, clause 11 |
| --- | ---: | ---: |
| Robustness of the Solution and Quality of Guardrails | 30% | 30% |
| Architecture and Performance Efficiency | 20% | 20% |
| Security Reporting | 20% | 20% |
| Completeness of the Self-Testing Suite | 15% | 20% |
| Practical Implementability and Scalability | 15% | 10% |

The documents disagree on the last two weights. Do not silently choose a column,
calculate a self-score, or claim a resolved official weighting. A film can show
all five criterion names without percentages. If percentages are needed for the
submission, identify both sources and ask the organizer to resolve the difference.

The criteria also require a simple architecture diagram, a documented sample
policy, a dashboard, and an executable suite with positive and negative cases.
Section 6 explicitly anticipates judges changing configuration or feeds, trying
unprepared prompts, and reviewing performance telemetry. The rules require a
maximum ten-slide PDF plus the project title, team name, member list and project
description. The seven-slide v2 PDF satisfies the slide-count limit only; it does
not replace the separate submission fields or the requested architecture diagram.

## Scene and evidence map

| Official need | Observable effect to show | Existing evidence and honest boundary |
| --- | --- | --- |
| Central policy source and dynamic controls | Identical `Hello`: ALLOW under v4, activate local text rule, BLOCK under v5 with upstream not executed. Show the version and reason beside the result. | Actual same-process recording: [demo-evidence.json](output/demo-evidence.json), original footage 10–39 seconds. The rule is deterministic. This is a real decision flip without restart or agent-code modification. |
| Hybrid deterministic and semantic guardrails | After the local rule example, show a natural-language financial rule, allowed/blocked expectations, before/after results, diff and explicit activation. | Eight scoped cases pass in the actual review, covering model/tool input/output. The financial blocked example was already blocked by the base policy. This proves review and saved regression workflow, not a newly caused semantic flip or arbitrary-rule accuracy. [Recorded review](output/demo-evidence.json). |
| Data privacy, input and output protection | Two-page PDF contains two synthetic emails. Protected Markdown replaces both. Completion gives a useful Qwen summary with Laya input/output passed. | [OCR evidence](output/ocr-demo-evidence.json), [exact downloaded Markdown](output/demo-document-approved.md). Extraction has no business call; completion does. Local OCR sees the original file; the business model receives protected text. This is redaction, not reversible-key recovery or edited PDF pixels. |
| Budget and resource governance | Show a real exhausted-budget denial, the usage/limit, no upstream execution, then a reviewed budget increase and successful repeat if captured. | Existing regressions: [test_budgets.py](../tests/unit/test_budgets.py), including atomic reservations and parallel enforcement; current queue evidence below. The existing policy/OCR movie does not show an exhausted-budget decision. Label a test result as a test, not as footage of a budget interaction. |
| Historical attack signatures / externally managed feed | Show one actual known-signature block with the matched control and upstream not executed, alongside a harmless allowed example. If showing feed reload, show its version changing. | [Signature tests](../tests/unit/test_signature_matching.py) cover encoded variants, bounded decoding and safe near matches; sample [feed](../examples/docs/signatures.json). They establish matching behavior, not complete prevention of every named vulnerability. No current film scene demonstrates a feed edit. |
| Security reporting and auditing | From the blocked request, open Activity and show reason, policy version, upstream flag, resource/queue fields; export actual JSONL if included. | Actual [audit screenshot](assets/demo-audit.png) and original movie around 39–45 seconds. UI records explain the execution boundary. Export capability is implemented, but an unrecorded export must not be presented as a filmed action. Audit excludes raw prompts and credentials. |
| Executable positive/negative self-tests | Show the command, installed package version/import origin, then real collected/passed output and a few named allow/block/redact/budget/signature cases. | Release 1.0.7 source evidence: 1,484 passed, 93.28% coverage; separate public-package verification: 406 security/admission/transport checks. [Release report](../evaluation/results/request-queue-1.0.7.json); sanitized private report `state/private/queue-package-1.0.7-pypi.json`. Do not sum counts or imply 406 model-accuracy prompts. A fresh filmed run needs its own exact count. |
| Easy integration with agents, MCP and models | Show a short real OpenAI SDK client pointing at the gateway, then the actual protected result. Optionally show the MCP client/tool pair using the same policy. | Ready examples: [OpenAI client](../examples/docs/openai_client.py), [MCP client](../examples/docs/mcp_client.py), [FastMCP server](../examples/docs/fastmcp_server.py), [ACP client](../examples/docs/acp_client.py). Actual installed public-package 1.0.7 integration passed: OpenAI SDK 3.24.0 called the protected `/v1` endpoint; `Hello` returned HTTP 200 under v1 with real Qwen and both Laya checks, then HTTP 403 under v2 with upstream false after the local rule activated. Same gateway, two semantic assessments. [Execution evidence](output/integration-demo-evidence.json) and [transcript](output/integration-demo-transcript.txt). The film renders code/results from this transcript, not a live terminal capture. MCP/ACP examples exist but this integration scene does not film them. Authentication remains in environment variables; values are not displayed. |
| Reliability while policies change | Invalid configuration keeps the active snapshot; queued work rechecks the latest policy; repeated initialization preserves policy, credentials and keys. | [Policy validation](../tests/integration/test_policy_validation.py), [queue integration](../tests/integration/test_request_admission.py), [startup preservation](../tests/unit/test_one_command_startup.py). The v2 operations scene is explicitly an editorial summary of regression-tested behavior. Idempotent setup does not mean deduplicated business requests. |

A compact, clearly labelled architecture view should show an app or agent,
FastFence input/output controls, and the model or tool, with central policy feeding
the control layer. This addresses the requested diagram and explains why pointing
a client at the gateway changes the protection boundary. The diagram is explanatory,
not a screen capture of a runtime tracing system.

## Recommended figures: two current checks and one optional historical timing

Use at most these three headline figures. The first two are scheduling/integration
verification, not latency benchmarks. Put their labels on the screen while their
numbers appear, not only in the description.

| Headline | Visible scope | Exact source |
| --- | --- | --- |
| **1,000 / 1,000 completed** | FastFence 1.0.7 controlled scheduling test. Eight active, 992 observed waiting. Synthetic provider, no model inference. | `controlled_burst` in [request-queue-1.0.7.json](../evaluation/results/request-queue-1.0.7.json); `test_one_thousand_distinct_identity_requests_wait_and_complete` in [queue integration test](../tests/integration/test_request_admission.py). This is source-test evidence, not a claim that 1,000 public-package model generations ran. |
| **12 / 12 real requests** | FastFence 1.0.7 candidate wheel outside checkout. Laya/Qwen3:4b input/output plus Qwen3:0.6b generation. Twelve benign requests, two admitted at once, 24 assessments. | Same [queue report](../evaluation/results/request-queue-1.0.7.json). Ten requests waited; final active/waiting/inflight counters are zero. 17.775 seconds is the whole observed run, not per-request p95. The report does not record hardware/OS, so do not invent a platform label for this check. |
| **Historical p95 0.248 ms** | Public PyPI **1.0.2**, Apple M3 Pro, macOS arm64, Python 3.12.12. Direct Python deterministic controls, 2,000 measured calls after 100 warmups, concurrency one. Semantic assessment off; no ingress HTTP or business-model generation. | [Installed-package comparison](../evaluation/results/installed-package-1.0.2-comparison.json), row `deterministic / zero_wait_fixture / allowed_business / concurrency=1`. Exact p95: **0.2475 ms**. The 31-byte allowed payload and constant fixture measure one narrow path, not general production latency. |

Suggested first screen copy:

```text
QUEUE AND REAL-MODEL VERIFICATION
FastFence 1.0.7

1,000 / 1,000 controlled requests
8 active, 992 waiting • synthetic provider, no inference

12 / 12 real requests
Candidate wheel • 24 Laya assessments • 2 admitted at once

Separate workloads. Integration checks, not throughput guarantees.
```

If the film includes the historical timing, give it a separate screen:

```text
HISTORICAL LOCAL-CONTROL TIMING
Public FastFence 1.0.2 • Apple M3 Pro

p95 0.248 ms
2,000 calls • 100 warmups • concurrency 1
Direct Python • deterministic controls • 31-byte allowed input
No HTTP, semantic inference or business-model generation
```

Do not graph these three values on a shared latency axis, infer a speedup from the
unprotected fixture, or promote the historical timing to version 1.0.7. If a fresh
benchmark is recorded later, replace this screen only after reviewing the actual
version, platform, workload, sample count and output JSON.

## Remaining boundaries

Semantic false positives and false negatives remain, particularly for compound
natural-language conditions. Passing the recorded eight examples does not establish
unseen-case accuracy. The historical 400-case development corpus is not a fresh
independent 1.0.7 evaluation. Memory budgets and retained audit are process-local;
restart resets them. Output filtering cannot undo a tool action that already ran.
These belong in the evidence description and one concise end caption, not as an
unsupported certification or a reason to hide successful observed behavior.

No new tests, model calls, benchmarks, product source edits or PDF edits were made
by this mapping review. The integration owner performed the separately recorded
actual run linked above. The film distinguishes unchanged UI footage, rendered
code/results from the actual integration transcript, and labelled explanatory
graphics. The self-testing summary refers to the filmed allowed/blocked example
review before activation, not a new filmed execution of the full test suite.
