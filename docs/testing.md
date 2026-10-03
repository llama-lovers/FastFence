# Testing and validation

## Automated suite

From the repository root:

```sh
uv sync --locked
uv run pytest -q
```

The optimized gateway and reproducible-demo checkpoint passes **413 tests**, with **95.59%** first-party source coverage. The configured coverage gate requires **85%**. Tests use an isolated offline policy and local fixtures; a running Ollama server or external account is unnecessary.

The suite covers positive and negative privacy cases, credential detection and redaction, role and tenant boundaries, model/tool allowlists, all five budget limits, concurrent reservation safety, immutable snapshots, dynamic configuration, invalid-update retention, source failures and deadlines, sanitized audit, and protocol behavior. Model request wire tests use explicitly controlled responses; those tests verify integration contracts rather than live inference accuracy.

The detect-secrets regressions additionally check GitHub/Slack credential formats, nested keys and values, Unicode and bounded line wrapping, caller allowlist-comment bypass attempts, disabled privacy, detector failures, no request-time I/O, concurrent use, and size bounds after redaction.

## Quality and architecture gates

```sh
uv run ruff check src tests
uv run basedpyright
uv run lint-imports
uv run pre-commit run --all-files
```

Pre-commit includes formatting, type checking, architecture checks, staged-specification coverage, and offline repository secret scanning. The reviewed `.secrets.baseline` contains known synthetic fixtures and public revision hashes. New findings require review; the hook does not regenerate the baseline automatically.

Architectural checks enforce the layer boundaries and reject first-party dataclasses and database imports in the memory-only runtime. Changes must be covered by a staged implemented or verified specification. See the [architecture](architecture.md) for the source layout.

## Real-model checks

With Ollama running and Qwen3:4b installed:

```sh
uv run python evaluation/run_semantic.py \
  --model qwen3:4b \
  --output evaluation/results/local-semantic.json

uv run python evaluation/smoke_hybrid.py \
  --output evaluation/results/local-hybrid.json
```

The historical binary-schema Qwen3:4b development run classified 20 synthetic probes correctly: 10 benign and 10 attack cases. Its median was 343 ms and p95 1,384 ms on the development machine. This small development sample does not establish general detection accuracy. The earlier numeric-score prompt missed all 10 attacks; its report remains available alongside the improved run.

The recorded memory-runtime hybrid smoke and original actual Laya integration each passed five cases. These historical checks predate the detector and authored-rule changes; they establish those integration checkpoints, not a fresh combined run of all current controls. They use actual local model inference; business tools remain simulated. The Laya runner and prerequisites are described in [integrations](integrations.md).

Public source reports:

- [Binary-schema semantic probes](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/qwen3-4b-binary-schema.json)
- [Original numeric-schema probes](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/qwen3-4b-initial-numeric-schema.json)
- [Memory-runtime hybrid smoke](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/hybrid-gateway-memory-smoke.json)
- [Actual Laya report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/integrations/laya/results/live.json)

## Current semantic severity and real threshold changes

```sh
uv run python evaluation/run_severity.py --split holdout --output evaluation/results/local-severity.json
uv run python evaluation/smoke_semantic_strictness.py --output evaluation/results/local-strictness.json
```

The `severity-v1` rubric maps `benign`, `suspicious`, and `malicious` to ordinal codes 0, 0.6, and 1. These are not calibrated probabilities. Prompt and corpus digests accompany the reports; the prompt and all labels were frozen before the holdout run. This is a self-authored synthetic PL/EN set, not an external benchmark.

The [60-case holdout](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/semantic-severity-holdout.json) had zero provider errors and 46 exact category matches. All 20 clearly malicious cases were classified malicious; 12 expected-suspicious cases were classified benign. Threshold 0.5 produced two false positives and twelve false negatives under the predeclared labels; threshold 0.8 produced one false positive and zero false negatives. The higher threshold's definition permits the suspicious category, so these figures describe different policies and are not interchangeable accuracy claims.

The separate [six-case strictness smoke](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/semantic-strictness-live.json) uses actual Ollama assessment through HTTP handlers and versioned policy updates. The identical suspicious development example is blocked at 0.5 and allowed at 0.8; benign and malicious examples retain their expected decisions. This proves configurable behavior, not independent accuracy. Business-tool data is simulated and audit metadata is sanitized.

## Policy studio and selective controls

First complete the [Laya and two-model setup](getting-started.md#describe-a-rule-then-test-it-through-mcp), with Ollama running. For a real browser walkthrough, install the optional test browser and run:

```sh
uv run --with playwright python -m playwright install chromium
uv run --with playwright python evaluation/smoke_policy_studio.py --live --output evaluation/results/local-policy-studio.json
```

The test starts an isolated gateway and temporary credentials. Actual Laya drafts a Polish text policy through the dashboard, examples are previewed, changing examples invalidates review, and explicit activation publishes the stored proposal. The model playground proves denial before upstream execution and displays the correlated audit trail. The runner also checks the model completion MCP tool with a bounded actual Qwen response. Browser-contract fixtures are reported separately and never labeled model inference.

## Operational benchmark

```sh
uv run python evaluation/benchmark_gateway.py \
  --output evaluation/results/local-runtime.json
```

The detector-enabled core baseline in the [detect-secrets runtime report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/detect-secrets-runtime-benchmark.json) measures 24,000 timed invocations, with 100 excluded warmup calls per scenario. It exercises actual Engine decisions, memory reservation/settlement, and bounded audit at concurrency one and eight. Semantic analysis is disabled; the offline secret detector is enabled. This report predates authored text rules and does not measure a gateway configured with those rules; the separate matcher benchmark below does not measure their combined cost either.

On an Apple M3 Pro with 18 GiB memory and Python 3.12.12, the serial zero-wait fixture measured:

| Workload | p50 | p95 | p99 | Requests/s |
| --- | --- | --- | --- | --- |
| Allowed business call | 0.132 ms | 0.142 ms | 0.160 ms | 7,531 |
| Signature denial | 0.016 ms | 0.016 ms | 0.018 ms | 62,596 |
| Role denial | 0.011 ms | 0.011 ms | 0.011 ms | 91,677 |

The zero-wait upstream is a labeled benchmark fixture using real tool authorization/validation and constant safe output. A separate mode uses the actual demo backend, including its intentional 15 ms wait. Direct core measurements exclude HTTP/MCP transport, DTO parsing, startup, and LLM inference. Outcomes, budget charges, and audit retention are checked so unexpected budget denials cannot appear as fast allowed requests.

These are development measurements for fixed small inputs, not a production latency guarantee. Other processes and CPU power state are uncontrolled. The earlier [memory-runtime report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/memory-runtime-benchmark.json) predates detect-secrets and must not be presented as current detector performance.

## Authored rules: actual inference and local enforcement

After setting up the pinned Laya engine and pulling Qwen3:4b and Qwen3:0.6b, run:

```sh
uv run python evaluation/smoke_authored_rules.py \
  --output evaluation/results/local-authored-rules.json
```

This starts an isolated real HTTP gateway with temporary credentials. Actual Laya/Qwen3:4b drafts a rule from Polish; the script validates its intended semantics and activates the exact saved proposal without a second inference. It then checks input denial, Unicode normalization, a real allowed one-token Qwen response, output blocking after real inference, and immediate rule removal. Semantic scanning is disabled so the report can prove the authored predicate adds no assessor calls. The report omits prompts, generated text and credentials.

The [recorded full run](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/laya-authored-rules-live.json) passed all five enforcement cases. Drafting took 3,635 ms; activation of the saved proposal used zero inference time. Separate authoring probes cover an unseen literal and rejection of a broad compliance instruction. The [initial report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/laya-authoring-probes-initial.json) preserves a rejected scope mismatch; the [follow-up report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/laya-authoring-probes.json) explicitly identifies which probe was rerun after constraining generation scope.

Authoring is a one-time management operation and can take seconds or tens of seconds on the local model. It is not the latency of runtime rule matching. To measure the latter separately:

```sh
uv run python evaluation/benchmark_text_rules.py \
  --output evaluation/results/local-text-rules.json
```

The [recorded local matching benchmark](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/authored-text-rules-benchmark.json) uses 2,000 measured iterations plus 100 warmups for each combination of 1/16/64 rules and 128 B/4 KiB/64 KiB content. All predicates miss; case handling is mixed. At 4 KiB, p95 was 0.002625 ms for one rule, 0.031166 ms for 16 rules and 0.075 ms for 64 rules. This measures the matcher only, excluding transport, other controls, accounting, auditing and inference. Fixed ASCII inputs and uncontrolled machine load make it development evidence, not a universal latency guarantee.

## Historical exploit variants

```sh
uv run python evaluation/validate_historical_attacks.py --output evaluation/results/local-historical.json
```

The same 38-case inert corpus is retained for the [before](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/historical-attack-validation-before.json) and [after](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/historical-attack-validation.json) reports. Detection improved from 10/30 to 30/30 desired attack variants, including whitespace, Unicode, bounded encoding and adjacent list fragments. Six benign near-matches pass; two quoted dangerous patterns remain conservative false positives. Nothing is executed or unpickled. The matcher decodes bounded text views only, and the corpus is not an external exploit benchmark.

## Actual HTTP and MCP transport

```sh
uv run python evaluation/benchmark_transport.py --samples 100 --warmup 20 --output evaluation/results/local-transport.json
```

The [transport report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/transport-benchmark.json) exercises isolated uvicorn processes over loopback TCP with actual HTTP and JSON-RPC MCP requests, offline secret detection and the bounded signature matcher. It covers 0/1/64 authored rules, short/~8 KB payloads and concurrency 1/8. All 76 groups passed their expected outcomes with zero transport errors or unexpected verdicts. Warmups are excluded from timing and included in budget/audit reconciliation.

Across configurations, 7,680 business invocations produced 2,880 allowed and 4,800 blocked decisions, exactly 7,680 audit entries, 23,466,240 settled token units and 288,000 configured micro-USD cost. No semantic model ran and no reservations remained in flight. Allowed calls include the simulated business backend's intentional 15 ms delay.

| Measured scope | Allowed-call p95 range | Blocked-call p95 range |
| --- | --- | --- |
| HTTP, across all payload/rule/concurrency groups | 20.7–110.1 ms | 1.13–17.09 ms |
| MCP, across all payload/rule/concurrency groups | 24.8–131.1 ms | 1.92–40.17 ms |

These ranges span different workloads; the report retains every group. They are not pure guardrail overhead and do not establish a universal latency SLA. Health and authenticated MCP ping are labeled non-equivalent transport baselines and are never subtracted from business-call measurements. Client serialization, transport, response decoding and server execution are included; the local machine is not a controlled production benchmark environment.

## Scan optimization and current transport checkpoint

The [core before](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/scan-optimization-before.json) and [core after](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/scan-optimization-after.json) reports cover the same eight configurations, each with 200 measured calls and 20 warmups. A request-local base64 memo avoids repeated identical decodes while preserving all resource counters. The pinned default keyword detector skips its assignment regexes only when a required quote or denylisted keyword is absent; unsupported versions/configurations retain the original scan. All 19 credential plugins remain enabled. Differential tests compare exact upstream candidates and complete redacted output/findings over 460 keyword/syntax/Unicode samples plus nested credential cases.

For 8,000-byte clean inputs, core p95 fell from 5.93–6.24 ms to 2.05–2.41 ms across 0/64 rules and concurrency 1/8. This includes authorization, validation, input/output inspection, budgets and audit with a zero-wait upstream fixture; it excludes HTTP/MCP. Short-input results are mixed: one 64-rule serial group changed from 0.203 to 0.219 ms p95, with its noisier tail retained in the report.

The subsequent [optimized transport report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/transport-optimized.json) repeats all 76 groups with the same 100 samples and 20 warmups. All 7,680 invocations and audit entries reconcile, with zero unexpected verdicts, transport errors, semantic calls or pending reservations. The earlier transport report above remains the pre-optimization checkpoint.

| Allowed request, 64 rules, 8,000 bytes | Earlier p95 | Optimized p95 |
| --- | ---: | ---: |
| HTTP, concurrency 1 | 29.80 ms | 29.80 ms |
| HTTP, concurrency 8 | 106.52 ms | 41.43 ms |
| MCP, concurrency 1 | 30.48 ms | 29.97 ms |
| MCP, concurrency 8 | 114.55 ms | 42.03 ms |

Across the optimized matrix, allowed HTTP p95 spans 22.90–41.43 ms and MCP 24.62–44.30 ms. Blocked HTTP p95 spans 1.06–27.48 ms and MCP 1.63–35.79 ms. These remain full transport measurements including the allowed demo backend's intentional 15 ms wait, on one development machine; they are not a universal latency guarantee.

The [final combined hybrid rehearsal](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/hybrid-final-rehearsal.json) also passed five cases using actual Qwen3:4b with the current detector and feed: allowed business input, semantic attack denial, output redaction, role denial and an allowed real completion. Audit export remained sanitized. Business handlers are simulated, and this live check is separate from deterministic timing.
