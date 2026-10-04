# Metric inventory and interpretation

All definitions below come from the current [ledger](../src/fastfence/modules/control/persistence/ledger.py), [status assembly](../src/fastfence/modules/control/application/use_cases/management.py), [request admission](../src/fastfence/modules/control/application/services/admission.py) and [dashboard renderer](../src/fastfence/app/interfaces/http/web/console.js).

## Invocation counters

`GET /api/admin/status` exposes these under `metrics`:

| Field | Unit / window | Meaning |
|---|---|---|
| `requests` | Finished invocation decisions; cumulative since process start | Counted when the engine appends an invocation verdict. Not a count of every incoming HTTP request: management traffic and requests rejected before entering the engine are different. |
| `allowed`, `blocked`, `redacted`, `errors` | Decisions; cumulative | Mutually exclusive final invocation categories. Their sum equals `requests`. Management audit events do not increment them. |
| `local_only_requests` | Decisions; cumulative | Both semantic stage statuses are `not_run`. Includes early local blocks; it does not mean every request reached an upstream service. |
| `semantic_requests` | Decisions; cumulative | At least one semantic stage differs from `not_run`, including a semantic error. `local_only_requests + semantic_requests = requests`. |
| `semantic_calls` | Assessment invocations; cumulative | Counts calls to the semantic assessment boundary, including attempts which fail. A request can perform multiple assessments; rule-review/management assessment work can also contribute. This is not a count of requests, successful predictions or business-model calls. |
| `throughput_rps` | Finished decisions per second | Recent completed invocations over a rolling window up to 60 seconds. During startup, divides by elapsed process time rather than a full 60 seconds. |
| `throughput_window_seconds` | Seconds | Actual denominator used for throughput; returned rounded to three decimals. |
| `p95_latency_ms` | Integer milliseconds | Nearest-rank p95 of the most recent at most 2,048 invocation decisions. Includes queue waiting and upstream execution; excludes gateway transport overhead. This is **not** isolated guardrail overhead. |
| `latency_sample_size` | Decisions, 0–2,048 | Number of retained latency observations. Empty ledger returns p95 zero; dashboard displays a dash rather than a measured zero. |
| `audit_retained` | Events | Current bounded audit-ring size, including invocation and management events. |
| `audit_dropped` | Events | Total appended events minus retained events; older events have been evicted from this process. |

The dashboard displays the two path counters as percentages of `requests`. It separately renders Requests/s rounded to two decimals, and labels the latency sample window. Top denial reasons are the five most frequent blocked-invocation reasons **among the latest 200 loaded audit events**; management rows are excluded. This is a recent-window summary, not lifetime threat prevalence or a classifier-accuracy measurement.

## Audit records

The [Verdict schema](../src/fastfence/modules/control/domain/models.py) supplies security fields. The ledger appends:

- Correlation: `sequence`, UTC `time`, `request_id`, `instance_id`, `subject`, `tenant`, `target`, `event_kind`.
- Decision: `decision`, `reason`, `findings`, `policy_version`, `feed_version`.
- Timing: `latency_ms`, `queue_wait_ms`.
- Semantic outcome: `semantic_provider`, `semantic_score`, `semantic_input_status`, `semantic_output_status`.
- Execution/accounting: `upstream_executed`, `tokens`, `cost_microusd`.
- Privacy outcome: `anonymized`, `restored`.

`semantic_score` is an ordinal severity value, not a calibrated probability. `not_run` distinguishes a skipped stage from `passed`; a configured provider does not establish that a model was available. Read both per-stage values and the final reason.

A local input block can produce `upstream_executed=false`; an output block can occur with it `true`. Unknown provider failures retain conservative accounting when execution may already have occurred. An error is not blanket proof that retrying a side-effecting operation is safe.

The audit serializer explicitly excludes `output`. Raw prompt/argument bodies are not audit-record fields. Control findings contain names/identifiers, rather than the matching PII or secret value. The export is therefore minimized diagnostic metadata, not a promise that arbitrary operator-supplied metadata is anonymous.

## Queue snapshot

`status.request_queue` is a current process snapshot, not cumulative traffic:

| Field | Unit / meaning |
|---|---|
| `active`, `max_active` | Currently admitted requests / configured global active capacity. |
| `waiting`, `max_waiting` | Requests currently waiting / configured queue capacity. |
| `wait_timeout_ms` | Configured maximum admission wait in milliseconds; UI shows seconds. |
| `per_identity` | Maximum waiting requests per trusted identity. |
| `waiting_bytes`, `max_waiting_bytes` | Accounted queued payload bytes / configured byte bound. These are not total process RSS. |

The queue uses FIFO admission among eligible identities. Separate per-identity concurrency, model-worker admission and tool-connection limits still apply. Queued work rechecks current policy before execution. The dashboard shows count/capacity and maximum wait; the API also includes byte bounds. Per-decision `queue_wait_ms` records actual waiting. Accounted compute time excludes that waiting, while total latency includes it.

## Budget rows

`status.budgets` contains usage for the current **UTC day**, keyed by trusted subject and process instance, together with effective limits and role names:

| Field | Unit / meaning |
|---|---|
| `calls` | Calls admitted to budget reservation. Early blocks may contribute a request verdict without consuming this count. It is not the dashboard's total `requests`. |
| `tokens` | Accounted token/resource units; reservations are settled against reported/bounded usage. Not necessarily identical to a provider's billed tokenizer count. |
| `cost_microusd` | Estimated micro-US dollars; 1,000,000 µUSD = 1 USD. Based on configured accounting, not an invoice. |
| `compute_ms` | Accounted compute duration in milliseconds, excluding queue wait. |
| `inflight` | Current subject reservations; compare against the effective concurrent limit. |
| `limits` | Effective calls/token/cost/compute/concurrency limits derived from the active policy and the subject's trusted roles. |

Reservations prevent concurrent work from overspending the local limits; totals visible during work can include reservations that later settle. A reload may change effective limits without resetting already-accounted usage. Multiple workers or hosts do not coordinate a shared global budget.

## Retention, refresh and operational scope

- Default audit capacity: **10,000** events; configurable bounded capacity up to 100,000. Status returns the newest **200** retained events. The current JSONL route exports at most the newest **10,000**, oldest-first within that exported subset—even if a larger ledger capacity is configured.
- All counters, budgets and audit storage are process-local memory. `runtime`/metric scope exposes `instance_id`, `telemetry_scope="instance"`, `storage="memory"`, reset behavior and `global_budget_coordination=false`.
- Restart clears the in-memory evidence. Export before restart if you need to retain it. This implementation does not claim durable SIEM storage or automatic cross-instance aggregation.
- The visible dashboard tab polls every five seconds. API reads return current snapshots; neither screen polling nor in-memory updates imply streaming delivery of every event.
- `/health` describes process liveness. `/ready` separately checks required semantic prerequisites without inference. Neither endpoint proves that all future requests will succeed; see the [integration reference](../docs/integration-reference.md).
