# Testing and validation

## Automated suite

From the repository root:

```sh
uv sync --locked
uv run pytest -q
```

The authored-rule checkpoint passes **271 tests**, with **94.52%** first-party source coverage. The configured coverage gate requires **85%**. Tests use an isolated offline policy and local fixtures; a running Ollama server or external account is unnecessary.

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

The recorded binary-schema Qwen3:4b development run classified 20 synthetic probes correctly: 10 benign and 10 attack cases. Its median was 343 ms and p95 1,384 ms on the development machine. This small development sample does not establish general detection accuracy. The earlier numeric-score prompt missed all 10 attacks; its report remains available alongside the improved run.

The recorded memory-runtime hybrid smoke and actual Laya integration each passed five cases. These checks use actual local model inference; business tools remain simulated. The Laya runner and prerequisites are described in [integrations](integrations.md).

Source reports (repository access is required while the repository is private):

- [Binary-schema semantic probes](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/qwen3-4b-binary-schema.json)
- [Original numeric-schema probes](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/qwen3-4b-initial-numeric-schema.json)
- [Memory-runtime hybrid smoke](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/hybrid-gateway-memory-smoke.json)
- [Actual Laya report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/integrations/laya/results/live.json)

## Operational benchmark

```sh
uv run python evaluation/benchmark_gateway.py \
  --output evaluation/results/local-runtime.json
```

The current [detect-secrets runtime report](https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/evaluation/results/detect-secrets-runtime-benchmark.json) measures 24,000 timed invocations, with 100 excluded warmup calls per scenario. It exercises actual Engine decisions, memory reservation/settlement, and bounded audit at concurrency one and eight. Semantic analysis is disabled; the offline secret detector is enabled.

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
