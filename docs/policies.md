# Policies and guardrails

## Configuration sources

FastFence reads `config/policy.yaml` and `config/signatures.json` at startup. A background worker checks for updates every two seconds by default. Each request acquires one deeply immutable policy/feed snapshot by reference; configuration reads and validation happen outside the deterministic request path.

Changed policy content requires a higher `policy.version`. Changed feed content requires a higher `feed.version`; a feed-only update can retain the policy version. Invalid updates, conflicting versions, and source failures preserve the last valid snapshot. Startup requires valid configuration.

The management dashboard can edit and save a local policy, incrementing its version. A management-authenticated `POST /api/admin/reload` requests an immediate reload. Configuration diagnostics show source kind, generation, refresh counts, and sanitized failure codes.

For a centrally hosted source, set `FASTFENCE_CONFIG_URL` to a trusted HTTPS endpoint. HTTP is accepted only for loopback. The endpoint must return a JSON object with exactly two fields:

```json
{
  "policy": {"...": "complete policy object"},
  "feed": {"...": "complete signature feed object"}
}
```

The illustration shows the envelope, not a valid policy. Both inner objects must satisfy the same schemas as the local files. Redirects are disabled and fetches have a complete-body deadline and size bound. Remote policy is edited at its source; gateway management saves cannot overwrite it.

Polling, timeout, size, identity, and upstream settings are documented in [settings](settings.md).

## Policy fields

| Field | Purpose |
| --- | --- |
| `tools` | Explicit business-tool allowlist, permitted roles, timeout, and estimated per-call cost. |
| `models` | Explicit completion-model allowlist, permitted roles, maximum output tokens, timeout, and estimated cost. |
| `budgets` | Per-role limits for calls, token units, micro-USD cost, runtime milliseconds, and concurrency. |
| `privacy` | Enable privacy checks and choose input/output `block` or `redact`. |
| `signatures_enabled` | Enable literal attack-signature checks on input and output. |
| `semantic` | Select `disabled`, `ollama`, or `kev`; configure assessor model, threshold, timeout, and output scanning. |
| `max_input_bytes`, `max_output_bytes` | Bound serialized UTF-8 payload sizes, including sanitized payloads. |

Every permitted role needs a budget. Client-provided roles, tenants, or headers cannot grant access: trusted identity records define those claims at startup. A role grant cannot authorize a target omitted from the active allowlist.

## Block and redact

The supplied policy blocks detected sensitive input and redacts sensitive output:

```yaml
privacy:
  enabled: true
  input: block
  output: redact
```

Change `input` to `redact` to forward sanitized content to the upstream. Change `output` to `block` to suppress a sensitive result. Increase the policy version when editing the file.

Privacy combines existing heuristics with **detect-secrets 1.5.0** through 19 offline credential-format and keyword detectors. It covers representative GitHub, GitLab, Slack, AWS, Azure, JWT, and private-key formats, alongside email and other heuristic patterns. Nested keys and values are inspected. Findings contain fixed detector names, never detected secret values.

Detector instances are constructed at startup. Runtime scanning makes no credential-verification requests, scans no files, and ignores repository baselines and caller-supplied allowlist comments. Detector failures block delivery with a sanitized reason. Disabling `privacy.enabled` disables both privacy components.

Unicode NFKC normalization is applied. Bounded line-wrap reconstruction covers one scalar string up to 4,096 characters and eight line breaks. Fragments across separate messages or fields are not reconstructed. Detection remains heuristic; it is not a universal secret or PII recognizer.

## Literal attack signatures

A signature is a case-normalized, Unicode-normalized literal substring. It is not a regular expression or a whole-word matcher. Patterns must be 4–256 characters; the feed supports up to 200 entries.

For example, add an entry to the complete feed and raise its version:

```json
{
  "id": "restricted_project_name",
  "pattern": "Project Nightfall",
  "description": "Block this literal project name"
}
```

The rule applies to both input and output, including nested string values and dictionary keys. A matching input is blocked before upstream execution. A matching output is suppressed after execution; `upstream_executed` distinguishes those cases.

The supplied feed demonstrates instruction override, unsafe pickle/PyTorch loading, and remote-shell markers. These are specific pattern checks, not comprehensive prevention of code execution, supply-chain attacks, or prompt injection.

## Semantic controls

The default policy disables semantic checks. The hybrid profile enables a real separately hosted Ollama assessor. The current Ollama response schema produces a binary score: ordinary content `0`, attack `1`; this is not a calibrated risk probability. Invalid responses, timeouts, or configured provider failures fail closed.

Semantic checks supplement authentication, authorization, signatures, and budgets. They do not replace deterministic enforcement. The completion model and the assessor model are independently configured. See [testing](testing.md) for real-model evidence and its limits.

## Budget scope

Budgets are local to an instance, trusted subject, and UTC day. Atomic reservations prevent parallel invocations from spending the same remainder. Calls are charged at reservation; settlement releases unused allocations while failed or cancelled work retains conservative charges.

Token units are conservative accounting estimates, not an exact tokenizer count or provider invoice. Model reservations include 1,024 units for provider prompt-template overhead in addition to input bytes and bounded completion tokens; settlement releases unused capacity. `cost_microusd` is a configured per-call estimate; one micro-USD is $0.000001. Local models may use zero financial cost while retaining runtime and token limits.

Counters and bounded audit reset on restart. Multiple instances have independent allowances, with no global coordination. Output blocking cannot roll back upstream side effects. The [deployment guide](deployment.md) explains these operational boundaries.

## Authored text rules

Add bounded local rules to `policy.text_rules`. They use literal operators, never generated Python or arbitrary regular expressions:

```yaml
text_rules:
  - id: no-letter-a
    operator: word_contains
    value: a
    direction: both
    target: model
    action: block
    case_sensitive: false
```

This blocks a model request or response containing a word with `a`, including uppercase `A` and Unicode compatibility forms. NFKC normalization and optional casefold apply; accents stay distinct, so `ą` does not match `a`. Words consist of Unicode letters and combining marks. `contains` checks a literal substring of a scalar string; `equals` checks the entire scalar. A `word_contains` value must itself contain only letters or combining marks.

Choose `input`, `output`, or `both`, and `model`, `tool`, or `all`. Model inputs include prompt, message content and stop strings; model outputs include generated text. Roles, model identifiers and structural JSON keys are excluded. Tool rules inspect recursive string values, excluding dictionary keys. Existing signature and privacy controls keep their broader inspection scope.

At most 64 rules are permitted, each with a unique ID and a nonblank value of at most 128 characters. Literal preparation happens during validation. Matching needs no compiler, model, filesystem, or network call. Input blocks precede execution; output blocks suppress delivery after execution. Findings contain rule IDs, never matched content.

In the dashboard, select **Text rule**, set its scope and samples, then **Preview** and **Activate rule**. Preview evaluates only the candidate predicate: `NO MATCH` is not a promise that all other security controls will allow the request. Activation adds the rule to the current policy with a new version. Duplicate IDs, invalid rules and version conflicts are rejected. A remote configuration source must be updated at that source.

Management clients can retrieve `GET /api/admin/rules/schema`, then call `POST /api/admin/rules/preview` with a `rule` object and up to 16 `samples`, each at most 4,096 characters. Preview neither changes policy nor invokes a model. Publish a validated proposal through the existing versioned `PUT /api/admin/policy` endpoint.

## Draft a rule in natural language with Laya

The authoring CLI uses the pinned **actual Laya engine** and a real local Qwen model to produce an untrusted proposal in the rule schema above. This happens in the management plane. Once activated, the gateway performs only local literal matching for that rule.

Start the gateway and Ollama, install `qwen3:4b`, and run `integrations/laya/setup.sh` once. Then draft and preview:

```sh
integrations/laya/author-rule.sh \
  --instruction 'Blokuj każde słowo zawierające literę a, bez rozróżniania wielkości liter.' \
  --direction both --target model \
  --sample Hello --sample Cat \
  --save-proposal state/no-letter-a.json
```

The samples should return `[false, true]`: no match for `Hello`, match for `Cat`. Read the exact proposed rule locally before activation:

```sh
cat state/no-letter-a.json
integrations/laya/author-rule.sh \
  --proposal state/no-letter-a.json \
  --sample Hello --sample Cat \
  --activate
```

Saved-proposal activation revalidates and publishes **the same rule without a second model call**. It preserves other controls, increases the current policy version and rejects duplicate rule IDs or concurrent version conflicts. A saved proposal uses private file permissions (`0600`); do not publish files containing private policy literals. Reports omit instruction, literal value, samples and bearer credentials.

`--direction output` restricts responses only; `input` blocks before generation. Use `--target tool` for tool argument/result string values, or `all` for both. The model cannot widen the explicitly requested direction or target during drafting. Supported values are literal `contains`, `word_contains`, and `equals`; this is not a general compliance compiler. Unsupported or invalid proposals are rejected. A model can still misunderstand your intent: inspect the saved rule and preview representative allowed and forbidden examples.

Compilation connects directly to a separately trusted **loopback Ollama endpoint** using management-side Laya. It is outside the protected agent's quota and policy path so existing content restrictions cannot prevent authorized policy maintenance. Credentials, activation and preview use management-authenticated gateway endpoints. The local-only compiler integration uses isolated Laya settings/storage and a narrow Ollama compatibility adapter; it does not alter your normal Laya configuration.

To remove or change a rule, edit `text_rules` through **Manage policy** with an increased version, or update the configured central source. Changes apply to subsequent invocations.
