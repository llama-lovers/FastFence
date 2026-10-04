# Benchmarks

Measure FastFence on the hardware and policy you intend to use. A local text-rule lookup, a complete gateway invocation and a request assessed by Laya measure different work. The results below identify which path was timed.

## OFF / deterministic / semantic — package 1.0.2

Actual public PyPI package 1.0.2 measurements, recorded on 4 October 2026 on an Apple M3 Pro. Every row uses the same short synthetic input and tool response at concurrency 1. OFF and deterministic controls were measured together; Laya ran separately on the same machine.

| Mode | Samples + warmup | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | ---: | ---: | ---: | ---: |
| OFF — synthetic response | 2000 + 100 | 0.000125 | 0.000167 | 0.000208 |
| Deterministic controls ON | 2000 + 100 | 0.206125 | 0.247500 | 0.643750 |
| Laya semantic ON — input and output | 20 + 2 | 1117.160333 | 1199.532000 | 1222.141500 |

**OFF** bypasses all controls, identity validation, budgets and audit. It measures only a constant function response without I/O; values near timer resolution do not represent real model or API latency. Do not extrapolate production throughput from them. ON timings include the controls that executed; semantic additionally includes two real Qwen assessments. All three exclude gateway ingress HTTP/MCP transport and business-model generation. Laya timings include communication with local Ollama during assessment.

The [OFF and deterministic ON report](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-comparison.json) also retains concurrency 8 and the observed slower p99 tail. The [semantic ON report](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-semantic.json) has only 20 samples: its p99 is the largest observation, not a stable estimate of the tail. Environment and measurement details follow below.

## Package 1.0.2 results — 4 October 2026

The exported ZIP was run against **public PyPI package 1.0.2**, installed in a fresh environment outside the checkout. Import provenance, every expected verdict and budget accounting were verified.

Apple M3 Pro, 11 logical CPUs, 18 GiB RAM, macOS 27.0.1 arm64, Python 3.12.12, Pydantic 2.13.5 and detect-secrets 1.5.0. One process, 2,000 samples and 100 warmup calls per row: 12,000 measured calls and 600 warmups in total. Recorded at 00:12 UTC.

**Scope:** complete engine invocation through Python, detect-secrets, memory budgets and audit. Semantic assessment disabled; zero-wait synthetic tool response. No HTTP/MCP or business-model generation. Inputs contain 31, 45 and 38 bytes for allowed, signature and role workloads respectively.

| Path | Concurrency | p50 (ms) | p95 (ms) | Requests/s |
| --- | ---: | ---: | ---: | ---: |
| Allowed request | 1 | 0.204625 | 0.227500 | 4757.87 |
| Signature rejection | 1 | 0.031125 | 0.038167 | 29740.33 |
| Role rejection | 1 | 0.012000 | 0.015167 | 76225.32 |
| Allowed request | 8 | 0.203834 | 0.228625 | 4681.31 |
| Signature rejection | 8 | 0.031625 | 0.037333 | 27566.10 |
| Role rejection | 8 | 0.012042 | 0.014542 | 63487.61 |

The [complete JSON report](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-deterministic.json) also records p99, process memory and workload checksums. Higher concurrency did not improve throughput here: this is one process doing local CPU work. These timings do not represent the default Laya-assessed request path.

### Actual Laya input and output assessment

A separate run on the same machine and public package 1.0.2 used **Laya + qwen3:4b (Q4_K_M)**. Threshold 0.7, timeout 60 seconds, output assessment enabled. Each row contains 20 measured requests and 2 warmup calls at concurrency 1. Recorded at 00:13 UTC.

| Path | p50 (ms) | p95 (ms) | Requests/s | Assessor calls including warmup |
| --- | ---: | ---: | ---: | ---: |
| Allowed request, input and output assessment | 1117.160333 | 1199.532000 | 0.88 | 44 |
| Early signature rejection | 0.034042 | 0.042167 | 24451.13 | 0 |
| Early role rejection | 0.013000 | 0.017166 | 51847.05 | 0 |

The allowed request executes two real model assessments. Its `median_ms` was 1119.5705 ms; the table's p50 uses the nearest-rank method rather than averaging the two central observations. Early rejections do not call the model.

This is a small sample with a repeated fixed prompt and a warmed model; Ollama prefix/KV reuse may help. It does not describe cold starts, varied long conversations or attack-detection quality. The tool response remains synthetic. The [complete Laya report](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-package-1.0.2-semantic.json) contains the full model digest, configuration and accounting evidence.

## Run against an installed package

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then download the benchmark bundle. No FastFence source checkout or running gateway is required for the deterministic measurement.

```bash
curl -L https://fastfence.dev/downloads/fastfence-benchmarks.zip -o fastfence-benchmarks.zip
uv run --no-project --python 3.12 python -m zipfile -e fastfence-benchmarks.zip benchmarks
uv run --no-project --python 3.12 python benchmarks/scripts/benchmark_package.py \
  --pypi-version 1.0.2 --samples 2000 --warmup 100 --concurrency 1 8 \
  --output results.json
```

The launcher installs the exact public PyPI package into a fresh temporary environment, verifies that `fastfence` imports from its installed package, and executes the bundled workload outside your project. It creates separate synthetic policies and identities; it does not use or change your gateway configuration. It reports actual dependency versions, hardware, expected verdicts and accounting checks alongside the timings. Python dependencies may download on the first run; package installation is outside the timed workload.

The default run uses the deterministic pipeline and a zero-wait synthetic tool response. It measures local control work; it does not represent the default Laya-enabled product request path. Concurrency 1 and 8 are separate measurements, not a horizontal scaling test.

For an additional real Laya measurement, start Ollama and run this command when the model is otherwise idle:

```bash
uv run --no-project --python 3.12 python benchmarks/scripts/benchmark_package.py \
  --pypi-version 1.0.2 --semantic --samples 20 --warmup 2 --concurrency 1 \
  --output semantic-results.json
```

This run prepares the configured assessment runtime and model in its isolated workspace. Its model calls, warmup and measured requests can consume substantial time and memory. The upstream tool response remains synthetic, so this measures semantic control plus the local invocation, not business-model generation. Twenty samples provide only an exploratory latency estimate; retain the model and environment metadata and increase samples for a meaningful tail comparison.

## Read the measurements

- **p50** is the 50th percentile of request latency (nearest-rank in these reports): half of the measured requests completed within this time.
- **p95** is the latency at or below which 95% of measured requests completed. It describes the slower requests better than the mean.
- **p99** is the 99th percentile; small samples cannot reliably characterize such rare delays.
- **Throughput** is completed requests divided by elapsed wall time, reported as requests per second. Concurrency can increase throughput while also increasing individual request latency.
- **Warmup** runs prepare the runtime but are excluded from the latency sample. Their effects on caches, audit and budgets still matter.

The engine benchmark measures complete in-process invocations, including configured controls, memory budget reservation/settlement and bounded audit. It excludes HTTP/MCP transport, process startup and configuration loading. The zero-wait fixture returns a fixed synthetic response; the delayed fixture deliberately waits 15 ms. Neither fixture measures a business model.

Laya assessment requires separate measurements with its real configured model. Enabling semantic controls adds inference time and may change the decision path. A request rejected by a deterministic rule can skip the model entirely. Report those paths separately; a fast input rejection does not establish the latency of an allowed model request.

## Behavior verification alongside performance

Public package 1.0.2 passed **143/143 existing parameterized security regressions**, with no skipped cases. Tests ran in a fresh environment outside the checkout; network connections were blocked and service/semantic boundaries were controlled by the tests. This verifies permissions, blocking, redaction, budgets, signatures and control composition — not 143 novel attacks or model detection accuracy. [Installed-package security report](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-security-1.0.2.json).

A separate actual one-command package run verified Laya, OCR and live policy updates without restarting: **ALLOW v1 → BLOCK v2 → ALLOW v3 → budget block v4 → ALLOW v5** in the same instance. Repeated startup preserved private state. The [actual lifecycle report](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/installed-one-command-1.0.2.json) contains outcomes only, without prompts, model responses or credentials.

## Recorded measurements from 3 October 2026

These are historical development measurements, **not results for the current package release**. The transport report identifies FastFence 0.1.0. The microbenchmark reports do not identify a package release; their raw reports and source are linked below.

The engine and transport reports record an Apple M3 Pro, 11 logical CPUs, 18 GiB RAM, macOS 27.0.1 arm64 and Python 3.12.12. They used one process; the selected rows below use concurrency 1. Background applications and CPU power state were not controlled.

| Measured path | Samples | p50 (ms) | p95 (ms) | Requests/s |
| --- | ---: | ---: | ---: | ---: |
| Engine, allowed request, detect-secrets enabled, zero-wait fixture | 2,000 | 0.131875 | 0.141625 | 7,530.61 |
| HTTP gateway, allowed request, simulated 15 ms backend | 100 | 25.022 | 29.191 | 39.041 |
| One literal rule, 128-byte input, no match | 2,000 | 0.001083 | 0.001250 | Not measured |
| 64 literal rules, 65,536-byte input, no match | 2,000 | 0.276750 | 0.317000 | Not measured |
| Reversible AES-GCM token, synthetic email, transform and restore | 1,000 | 0.035250 | 0.035875 | Not measured |

The engine row includes 100 excluded warmup calls; the HTTP row has 20, the rule cases 100, and the token case 100. The rule measurements exclude privacy checks, budgets, audit and transport. The token measurement excludes key initialization, matching over larger payloads, transport and model calls; it uses symmetric FFR1 tokens, not RSA envelopes.

Download the complete raw reports: [engine with detect-secrets](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/detect-secrets-runtime-benchmark.json), [HTTP/MCP transport](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/transport-benchmark.json), [literal text rules](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/authored-text-rules-benchmark.json), [stateless tokens](https://github.com/llama-lovers/FastFence/blob/main/evaluation/results/stateless-token-benchmark.json). They contain the measurement scope and additional cases; selecting these rows does not make the workloads equivalent.

## Make comparisons reproducible

Keep the raw JSON report with the package version, Python and dependency versions, CPU/OS/RAM, sample count, warmup, concurrency, payload size and enabled rules. For model-assisted measurements, also record the model, whether it was already loaded, and which input/output assessment stages executed. Compare the same workload and concurrency on the same machine.

Use enough samples to observe slower requests. A p95 from ten samples has very little information about the latency tail. Repeat measurements and retain errors or unexpected verdicts; successful HTTP responses can still represent blocked requests. Stop a comparison if its expected outcomes or budget accounting fail validation.

These numbers are observations on one development machine, not an SLA or a capacity guarantee. Do not subtract a health endpoint from a protected request to claim pure security overhead: those endpoints perform different work. Benchmarking throughput also does not measure security detection quality.
