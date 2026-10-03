# Testing and validation

## Automated suite

From the repository root:

```sh
uv sync --locked
uv run pytest -q
```

The stateless anonymization, OCR, policy regression and CI checkpoint passes **606 tests**, with **91.40%** first-party source coverage. The configured coverage gate requires **85%**. Tests use an isolated offline policy and local fixtures; a running Ollama server or external account is unnecessary.

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

## GitHub Actions

Every push to `main` and every pull request runs the locked Python 3.12 environment,
pytest with the 85% coverage gate, and the complete pre-commit suite: Ruff,
basedpyright, import-linter, Pydantic architecture checks, module size,
complexity, secret scanning, generated settings and lockfile validation.
CI fails if a hook rewrites tracked files. The specification gate checks the
committed change set against changed implemented specifications, including on PRs.
After verification succeeds, CI calls the documentation workflow to build MkDocs
strictly and deploy GitHub Pages at https://fastfence.dev/ from the same `main`
commit. Failed tests or linters prevent deployment. Documentation pull requests
receive a separate build without deployment. The workflow follows GitHub
[reusable workflow conventions](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).

Ordinary CI uses fake inference and OCR adapters; it does not download weights or
require private credentials. Real OCR and Qwen checks run locally as separate
integration evidence.

## Fresh-clone installation evidence

The [core acceptance report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/clean-install-core.json)
records a fresh clone of commit `fc4cddc36718d07fccd27a40f02cef44a1bcc71f`,
with no inherited `.env`, virtual environment, credentials or application state.
All ten checks passed: actionable missing-state diagnostics, repeated initialization
preserving private files, doctor validation, unauthenticated denial, an allowed
tool, injection denial, default anonymization, opt-in restoration, sanitized audit,
and restoration flags through actual MCP transport. Reproduce the core check with:

```sh
uv run python scripts/smoke_clean_install.py
```

An independent [fresh OCR installation report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/clean-install-ocr.json)
uses the same source commit. Its empty clone ran `uv sync --locked`,
`uv run fastfence init --anonymization` and `sh scripts/setup-ocr.sh`.
The installation created a new isolated OCR environment and model directory;
settings discovery worked without a `.env` file. The locked environment used
PaddleOCR 3.4.0, PaddlePaddle 3.3.0, Pydantic 2.13.5, Pillow 12.3.0 and
pypdfium2 5.13.0.

Actual extraction passed all **22 text/page checks across five synthetic fixtures**:
PNG, Polish JPEG, rotated PNG, scanned two-page PDF and mixed digital/scanned PDF.
Fresh-worker wall time was p50 **5557 ms** and p95 **5777 ms**. Each fixture ran
once; these timings include worker initialization and exclude HTTP and model
inference. They describe this local run, not general OCR accuracy or a latency SLA.

The document route was also exercised through FastAPI's in-process TestClient
with actual OCR: the default input-blocking policy returned 422 without Markdown;
changing input privacy to redaction returned 200 with both pages in order and
the synthetic email removed. No LLM was called in this OCR installation check.
Reproduce extraction after setup with:

```sh
state/private/ocr-env/bin/python -m fastfence.modules.ocr.interfaces.smoke \
  --python state/private/ocr-env/bin/python \
  --models state/private/ocr-models \
  --repeats 1 --output state/ocr-install-check.json
```

These reports establish clean installation for the core and OCR paths. They do
not establish fresh-clone Laya authoring or the complete real-model acceptance
flow; those require a separate successful `--full` run.

## Current stateless and document evidence

- [Actual Laya regression authoring](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/laya-regression-authoring.json): one synthetic instruction produced a valid letter rule and four independently passing local cases. Expectations were not repaired to force a pass.
- [Actual Qwen and document pipeline](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/live-anonymization-document.json): default output withheld the original name, opt-in restored an exact copied token, and real OCR Markdown reached the controlled model.
- [Local OCR extraction](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/ocr-local.json): five synthetic PNG/JPEG/PDF fixtures, 22 expected-text/page checks; fresh-worker p50 3166 ms and p95 3732 ms. This tiny fixture set does not establish general recognition accuracy.
- [Stateless token microbenchmark](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/stateless-token-benchmark.json): Apple M3 Pro, 1000 iterations per name/email workload, transform/restore p95 approximately 0.018 ms per operation. It excludes startup, transport and model latency. Recovery tokens expanded these short values by roughly 8–10 times in UTF-8 bytes; tokenization overhead is not measured.

For hands-on steps, use the [manual acceptance test](manual-testing.md).

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

## Current severity-v2 and frozen blind evaluation

With the pinned Qwen3:4b model available through local Ollama:

```sh
uv run python evaluation/run_severity.py --split holdout \
  --corpus evaluation/severity_holdout_v2.jsonl \
  --corpus-role independent_author_blind \
  --candidate-freeze evaluation/severity_v2_candidate.json \
  --expected-corpus-sha256 0bf738d27a112e830d447067d5bfaf1d18a6cb21f002e007827479f9f7e1b7a5 \
  --output evaluation/results/local-v2-holdout.json
uv run python evaluation/smoke_semantic_strictness.py --output evaluation/results/local-strictness.json
```

The candidate was selected on known development evidence and frozen before opening the new corpus. Its separate author used only the high-level severity definitions, without reading the developing prompt or new development cases. Dataset labels were frozen before candidate selection and before inference on that dataset. The runner verifies the selected prompt/model and expected corpus digests before inference. This is a separately authored synthetic blind holdout, not an external benchmark or representative production distribution.

The [v2 report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/semantic-severity-v2-blind-holdout.json) records **54/60 exact categories**, zero provider errors and all 20 clearly malicious cases detected. The 20 benign cases produced 18 benign and two suspicious classifications; the 20 suspicious cases produced 16 suspicious, two benign and two malicious classifications.

| Policy threshold | True positives | True negatives | False positives | False negatives |
| --- | ---: | ---: | ---: | ---: |
| 0.5: block suspicious and malicious | 38 | 18 | 2 | 2 |
| 0.8: block malicious | 20 | 38 | 2 | 0 |

The two missed suspicious cases concern internal sharing of a production connection string and retrying a payment whose earlier outcome is unknown. Overblocking includes two benign Polish metadata/reporting requests and two suspicious cases classified malicious. These mistakes remain in the report; the prompt was not tuned after seeing them. The thresholds define different expected-positive sets, so their counts are not interchangeable accuracy claims. Codes `0`, `0.6` and `1` are ordinal, not calibrated probabilities.

One development refinement was rejected despite higher overall exact accuracy because it missed a clearly malicious case. The [candidate freeze](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/severity_v2_candidate.json) and both development reports retain that decision. The original 72 cases are now known development evidence for v2; they must not be presented as a fresh v2 holdout.

The [v2 six-case strictness smoke](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/semantic-strictness-v2-live.json) uses actual Ollama through HTTP handlers. The same suspicious development example blocks at 0.5 and passes at 0.8 after a versioned live update; benign and malicious examples preserve their expected decisions. This proves configurable behavior, with sanitized audit, rather than independent accuracy.

### Historical severity-v1 checkpoint

The [original 60-case report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/semantic-severity-holdout.json) had 46 exact categories, zero provider errors and all 20 clearly malicious cases detected; 12 suspicious cases were classified benign. It remains unchanged. Because the v2 blind corpus is different, 46/60 versus 54/60 is not a controlled before/after accuracy comparison. The earlier [v1 strictness smoke](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/semantic-strictness-live.json) is retained separately.

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

The [severity-v2 combined hybrid rehearsal](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/hybrid-v2-rehearsal.json) also passed five cases using actual Qwen3:4b with the current detector and feed: allowed business input, semantic attack denial, output redaction, role denial and an allowed real completion. Audit export remained sanitized. Business handlers are simulated, and this live check is separate from deterministic timing.

## Dynamic configuration under sustained traffic

```sh
uv run python evaluation/soak_gateway.py --seconds 60 --output evaluation/results/local-soak.json
```

The [recorded soak](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/transport-soak.json) ran for 60.019 seconds with eight concurrent workers: 21,654 HTTP and 19,265 MCP requests. All 40,919 decisions were checked against their returned policy/feed snapshot. Every combination of five valid generations, six workloads and two protocols was exercised. Four valid updates changed privacy actions and signatures; invalid, rollback and oversized bundles preserved the last valid generation while background refresh continued.

Final accounting reconciled 20,464 charged calls, 3,253,839 token units and 2,046,400 estimated micro-USD, with zero pending reservations. The deliberately small audit ring retained exactly 128 records and evicted 40,791; its final sequence and request IDs matched returned decisions. The latency ring stayed at 2,048 samples. Server RSS sampled every two seconds ranged from 108.6 to 114.3 MiB. This single-process, one-minute development check uses a simulated 15 ms business backend and an atomic trusted HTTP configuration bundle; it does not establish long-term leak freedom or multi-instance quota coordination.

## Investigate a decision in the dashboard

From a playground result, choose **View this decision in audit**, or paste a request/rule ID into the decision-trail search. Filter by decision and open **Details** to inspect matched controls, upstream execution, policy/feed versions and sanitized identity metadata. Search stays in page memory and covers the latest loaded 200 events; the export contains the retained audit history. Expanded records survive refresh while they remain loaded.

The [audit browser fixtures](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/audit-ui.json) verify correlation, every decision-filter option, inert untrusted metadata, omission of unexpected payload fields, local search and mobile layout. Policy-review fixtures separately verify plain-language operation summaries, exact scope/case and the explicit limitation that content examples do not test role restrictions. These browser fixtures perform no model inference.

## Privacy and content-rule composition

Regression tests cover redaction introducing a forbidden literal or signature on model/tool input and output. They verify input denial before execution, output suppression after execution, settled reservations, retained sanitized findings and agreement with policy preview. Non-conflicting redaction still forwards useful sanitized content. Original content is also inspected, so redaction cannot erase a pre-existing denial. The recorded performance checkpoints above predate this added check on redacted payloads; clean payloads keep one restriction pass.

The [post-fix HTTP/MCP soak](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/transport-soak-composition.json) passes **39,221 mixed calls over 60 seconds**, including input/output redaction under changing policy/feed versions and failed refreshes. Budget settlement and bounded audit reconcile with no pending reservations. This verifies runtime behavior under this bounded workload; it is not a controlled throughput comparison with the earlier run.

## Bounded REST ingress and reloadable policy writes

Ingress regressions check authentication before any body consumption or JSON parsing, including malformed/deep JSON, management-role separation, actual streamed-byte limits with misleading or missing length headers, and valid escaped payloads. These transport checks precede the normal policy, budget and audit pipeline.

Policy persistence tests verify exact serialized byte boundaries, Unicode expansion and preservation of both the original file and active snapshot after an oversized management write. The retained configuration is then reloaded and used to construct a fresh policy store.
