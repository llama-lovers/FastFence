# Independent security review

Reviewed on 3 October 2026 against the working-tree changes since `5c225e9`,
including the subsequent FF-062 and FF-063 fixes and the FF-065/FF-066 scoped-rule
and semantic-preview additions, followed by the FF-070 upstream adapter,
FF-071 asymmetric tokens and FF-075 accounting correction. The review covered the console,
management authorization and policy updates, default runtime separation, and the
new Laya semantic worker. It was performed independently of implementation, using
synthetic credentials, temporary configuration and local fixture servers. Private
deployment credentials and configuration were not inspected or modified.

No confirmed P0 or P1 issue was found in the reviewed scope. Four confirmed P2
issues were reproduced, fixed and independently retested. This is a scoped review,
not a security certification or a guarantee that semantic classification detects
every attack.

## Confirmed findings and fixes

| Finding | Reproduction and consequence | Resolution |
| --- | --- | --- |
| P2: stale management save overwrote an unseen source update | Start with an active v1, write v2 with a stricter semantic threshold directly to the temporary policy file, then submit a stale v2 candidate. The old implementation accepted the save and erased the stricter source setting. | FF-062 pins the active base under the refresh lock and compares the actual persisted policy before substitution. The HTTP regression now returns 409, preserves the external file and permits a new save after explicit reload. |
| P2: missing completion state became an allowed classifier response | Return a valid benign severity object with `finish_reason: null` from an isolated HTTP model fixture. The actual installed Laya/LiteLLM path normalized the missing state to `stop`, and the worker accepted it. | FF-063 checks the original OpenAI SDK completion before LiteLLM and Laya normalize it. It requires one explicit stopped completion, a strict severity object and no tool, function or refusal mode. |
| P2: dependency dotenv loading defeated the worker environment allowlist | Import the installed LiteLLM initialization code from a temporary package tree containing a synthetic `.env`. A marker absent from the filtered child environment reappeared because LiteLLM defaulted to development mode and loaded dotenv. | The child environment now sets `LITELLM_MODE=PRODUCTION` and `PYTHON_DOTENV_DISABLED=1`. The same synthetic fixture no longer imports the marker. |
| P2: failed provider replies released the model token reservation | A provider returned malformed usage after processing a request. Under a 1150-token budget, two calls with a 1103-token reservation each executed and charged only 15 input units each. | FF-075 retains the full reservation after an attempted upstream operation fails without trustworthy usage. Real loopback HTTP regressions cover excessive usage, missing usage and provider errors; a second call is denied before another upstream request. |

The relevant implementation locations are
`src/fastfence/modules/control/persistence/policy.py`,
`integrations/laya/semantic_response.py`,
`integrations/laya/semantic_worker.py` and
`src/fastfence/modules/control/persistence/laya_semantic.py`.

## Independent validation

- Ran 71 focused tests covering the worker transport, deadlines, cancellation,
  concurrent rejection, invalid replies, management UI state, policy authoring,
  bounded persistence and product runtime. All tests passed. This subset command
  exited unsuccessfully only because it used the repository-wide 85% coverage
  gate; later subset commands explicitly disabled coverage.
- Ran another 118 tests covering REST ingress, MCP, OpenAI compatibility,
  caller/management separation, privacy, secrets, policy regression, semantic
  behavior and stateless controls. All passed.
- After the fixes, ran 59 focused tests covering source conflicts, persistence,
  reviewed policy activation, worker lifecycle and provider response validation.
  All passed. These groups overlap and should not be added as a unique-test count.
- Independently exercised the actual installed worker and pinned upstream Laya
  client against a synthetic HTTP provider. Null, missing and truncated completion
  states, tool calls, think-tag wrappers, duplicate severity fields and reasoning-only
  content were rejected. An explicit stopped severity response passed. Eight
  fixtures made exactly eight provider requests. The temporary HOME and working
  directory contained no created files, and a synthetic private input marker did
  not appear in stdout or stderr. These were protocol tests, not model inference.
- Exercised real Chromium with synthetic API fixtures. A rejected replacement
  management credential did not partially switch the agent identity. Injected HTML
  in policy data rendered literally without creating executable image/SVG nodes.
  Tokens were absent from local/session storage. Editing an output-scan setting
  after review disabled activation and cleared review confirmation.
- Inspected server authorization and the new UI rendering paths. Management
  endpoints require an administrator; protected invocation rejects administrator
  credentials. The reviewed UI uses text rendering for untrusted values. Browser
  checks do not replace those server-side controls.

Repeatable regression commands:

```sh
uv run pytest --no-cov -q tests/integration/test_policy_source_conflict.py tests/unit/test_policy_persistence_bounds.py tests/integration/test_policy_regression_diff.py tests/unit/test_laya_semantic_runtime.py tests/unit/test_laya_provider_validation.py
uv run --locked --with playwright==1.63.0 python evaluation/smoke_console.py --output state/private/console-browser.json
```

The additional adversarial HTTP, dotenv and browser probes described above were
run separately from these repository regression commands. No additional live-model
inference was performed by this reviewer. Recorded model outcomes in
`evaluation/results/laya-semantic-runtime.json` are implementation evidence, not
independent proof of general attack coverage.

## Scoped semantic rule and preview addendum

The subsequent FF-065 and FF-066 changes were reviewed separately. No additional
confirmed security blocker was found. Forty-nine focused tests passed for named
scope filtering, bounded rule context, required output scanning, worker lifecycle,
browser review state and the new management preview endpoint. Missing and agent
credentials are rejected before inference; stale initial versions and invalid
requests do not call the scanner. Preview failures do not write policy or execute
business operations.

Additional independent asynchronous browser-logic probes confirmed that changing
the rule or identity while inference is pending prevents the reply from enabling
review. Wrong-scope and wrong-version replies also cannot enable review. A policy
change before opening the final review is rejected. An isolated application probe
confirmed that an in-flight preview uses its captured snapshot and reports that
tested base version even if a newer snapshot appears during inference.

Named rules use the server-known invocation direction and model/tool type;
unrelated rules are omitted from the assessment. Preview assesses a sample with
applicable rules, rather than authorizing a protected invocation. Management
previews share the bounded single-flight worker and increment semantic-call
metrics, but are not charged to an agent's invocation budget. Their result neither
identifies which individual rule matched nor guarantees full runtime acceptance.

## Upstream and asymmetric-token addendum

The FF-070 adapter review checked fixed trusted upstream URLs, remote HTTPS and
loopback HTTP restrictions, secret settings, disabled redirects/environment
proxies, total deadlines, response byte bounds and strict usage validation. The
accounting issue above was found independently, reproduced and corrected before
publication. Validated successful usage still releases unused reservation;
unverifiable usage conservatively consumes the reservation, which can overcharge
an operation that failed before the provider performed inference.

The FF-071 review inspected RSA-3072 OAEP/SHA-256 key wrapping, fresh AES-256-GCM
content keys/nonces, distinct derived issuer authentication keys, authenticated
owner/rule/header scope, bounded canonical token parsing and constant-time issuer
HMAC validation **before RSA private-key operations**. Wrong owners, changed
rules, missing or rotated keys, altered tokens and expired tokens fail closed.
Token operations use preloaded keys without conversation storage. REST tests
exercise hidden-by-default output, permitted restoration, original-text hard-rule
reinspection, and no original/token material in audit output. The gateway requires
the private key for policy reinspection; this is not a public-key-only gateway.

Independent verification ran 81 tests covering the accounting correction,
semantic failure behavior, existing gateway behavior and new asymmetric unit/REST
cases, plus another 64 adapter, legacy-token and reinspection tests. All passed.
The real HTTP accounting fixtures use synthetic provider responses, and crypto
REST tests use a labeled echo backend; neither claims model-quality coverage.

```sh
uv run pytest --no-cov -q tests/integration/test_failed_provider_accounting.py tests/unit/test_model_template_reservation.py tests/unit/test_laya_semantic_runtime.py tests/integration/test_gateway.py tests/unit/test_asymmetric_anonymization.py tests/integration/test_asymmetric_anonymization.py
uv run pytest --no-cov -q tests/unit/test_openai_upstream.py tests/integration/test_openai_upstream_transport.py tests/unit/test_anonymization_tokens.py tests/unit/test_anonymization_reinspection.py
```

Only one RSA recipient pair is loaded: replacing it makes previously issued FFR2
tokens unreadable. Issuer-key rotation is separately bounded by the configured
keyring. Authenticated aliases preserve linkability within their owner/rule scope;
they are pseudonymization, not a claim of anonymous data. Deterministic output
restrictions and privacy block checks run again after restoration. Semantic
assessment receives protected text before restoration, not the recovered original.

## Remaining limits and trust assumptions

- Semantic inference can miss attacks or policy violations. The measured letter
  matching miss remains an explicit limitation; exact lexical restrictions should
  use deterministic text rules. Successful classification of one attack does not
  establish coverage of other wording, languages or encodings.
- The local model service and installed code are trusted deployment components.
  Provider HTTP bodies can be buffered before semantic response-size validation;
  the worker has no operating-system memory cap. Killing and reaping the worker
  bounds its lifetime, but does not independently guarantee that the model server
  immediately stops GPU work after a disconnect.
- The policy refresh lock serializes in-process writers. A separate filesystem
  writer must coordinate changes during the read-to-replace interval. FF-062 detects
  a source update already present when the save reads it; it does not implement a
  cross-process filesystem transaction.
- Budget and audit state are per-instance and in memory. Restarting the process
  resets them, and multiple independent instances do not share a global budget.
- The protocol fixture checked its temporary directories and captured streams.
  It was not an operating-system-wide filesystem or network trace. The no-SQLite
  guard and disabled upstream audit hooks were also inspected and covered by the
  focused tests.
