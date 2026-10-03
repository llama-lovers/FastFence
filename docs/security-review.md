# Independent security review

Reviewed on 3 October 2026 against the working-tree changes since `5c225e9`,
including the subsequent FF-062 and FF-063 fixes and the FF-065/FF-066 scoped-rule
and semantic-preview additions. The review covered the console,
management authorization and policy updates, default runtime separation, and the
new Laya semantic worker. It was performed independently of implementation, using
synthetic credentials, temporary configuration and local fixture servers. Private
deployment credentials and configuration were not inspected or modified.

No confirmed P0 or P1 issue was found in the reviewed scope. Three confirmed P2
issues were reproduced, fixed and independently retested. This is a scoped review,
not a security certification or a guarantee that semantic classification detects
every attack.

## Confirmed findings and fixes

| Finding | Reproduction and consequence | Resolution |
| --- | --- | --- |
| P2: stale management save overwrote an unseen source update | Start with an active v1, write v2 with a stricter semantic threshold directly to the temporary policy file, then submit a stale v2 candidate. The old implementation accepted the save and erased the stricter source setting. | FF-062 pins the active base under the refresh lock and compares the actual persisted policy before substitution. The HTTP regression now returns 409, preserves the external file and permits a new save after explicit reload. |
| P2: missing completion state became an allowed classifier response | Return a valid benign severity object with `finish_reason: null` from an isolated HTTP model fixture. The actual installed Laya/LiteLLM path normalized the missing state to `stop`, and the worker accepted it. | FF-063 checks the original OpenAI SDK completion before LiteLLM and Laya normalize it. It requires one explicit stopped completion, a strict severity object and no tool, function or refusal mode. |
| P2: dependency dotenv loading defeated the worker environment allowlist | Import the installed LiteLLM initialization code from a temporary package tree containing a synthetic `.env`. A marker absent from the filtered child environment reappeared because LiteLLM defaulted to development mode and loaded dotenv. | The child environment now sets `LITELLM_MODE=PRODUCTION` and `PYTHON_DOTENV_DISABLED=1`. The same synthetic fixture no longer imports the marker. |

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
