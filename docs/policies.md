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
| `semantic` | Select `laya` (product default), `disabled`, `ollama`, or `kev`; configure assessor model, threshold, timeout, output scanning and optional Laya-only instructions. |
| `max_input_bytes`, `max_output_bytes` | Bound serialized UTF-8 payload sizes, including sanitized payloads. |

Management writes also validate the exact serialized YAML size against the configuration source byte limit before replacing the file or active snapshot. An oversized candidate leaves the last valid source intact, so refresh and restart can still read it.

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

Redaction does not override content restrictions. The gateway checks the original content and then rechecks local text rules and signatures on a redacted result before forwarding or delivery. For example, a case-insensitive ban on `a` also rejects the `A` in `[REDACTED:pii_polish_id]`. Such an input is blocked before the upstream call; such an output is suppressed after execution. Preview uses the same order. Content without privacy findings does not incur this additional scan.

Privacy combines existing heuristics with **detect-secrets 1.5.0** through 19 offline credential-format and keyword detectors. It covers representative GitHub, GitLab, Slack, AWS, Azure, JWT, and private-key formats, alongside email and other heuristic patterns. Nested keys and values are inspected. Findings contain fixed detector names, never detected secret values.

Detector instances are constructed at startup. Runtime scanning makes no credential-verification requests, scans no files, and ignores repository baselines and caller-supplied allowlist comments. Detector failures block delivery with a sanitized reason. Disabling `privacy.enabled` disables both privacy components.

Unicode NFKC normalization is applied. Bounded line-wrap reconstruction covers one scalar string up to 4,096 characters and eight line breaks. Fragments across separate messages or fields are not reconstructed. Detection remains heuristic; it is not a universal secret or PII recognizer.

## Historical attack signatures

Threat feeds contain bounded text patterns, not executable rules or user-supplied regular expressions. The matcher applies NFKC/case normalization, strips common zero-width separators, and accepts up to eight whitespace characters between literal characters. Identifier boundaries avoid matching a dangerous identifier inside a longer ordinary name.

One layer of percent decoding and printable UTF-8 base64 decoding is inspected as text. Adjacent string siblings in a list can be reconstructed; unrelated dictionary fields are not joined. Limits on traversal depth/nodes, aggregate text, decoded content and views fail closed. These controls do not execute, deserialize or recursively decode payloads.

For example, add a pattern to the complete feed and increase its version:

```json
{
  "id": "restricted_project_name",
  "pattern": "Project Nightfall",
  "description": "Block the configured project-name pattern"
}
```

Patterns are 4–256 characters; the feed supports up to 200 signatures. The optional `match_mode: "token_sequence"` matches escaped whitespace-separated tokens with a bounded `max_gap` of at most 256 characters. The supplied shell signature uses `curl | sh` with that mode, allowing a URL between the command and pipe without accepting arbitrary regular expressions.

Input matches block before upstream execution. Output matches suppress delivery after execution; audit retains signature IDs and the `upstream_executed` flag. The same normalized matcher runs on a versioned external feed updated outside the request path.

The supplied patterns cover representative pickle/PyTorch loading, remote-shell and instruction-override strings. Quoted descriptions containing an exact dangerous pattern are conservatively blocked too. These are bounded text controls, not model-binary inspection or comprehensive exploit prevention. Before/after variant results are documented in [testing](testing.md).

## Semantic controls

The product policy uses **Laya with local Qwen3:4b**, a 30-second assessment timeout, threshold `0.7` and output scanning enabled. Requests first run local controls; content that reaches semantic inspection is assessed before forwarding, and generated output is assessed before delivery. Invalid responses, unavailable models, timeouts and provider failures fail closed. The completion model and assessment model are independently configured.

In **Policies → Edit configuration → Semantic analysis**, choose the provider and enter an optional natural-language policy in `semantic.instructions`. That field accepts up to 4,096 characters and requires provider `laya`; nonempty instructions with another provider are rejected. Review and activate the configuration change before testing representative allowed and prohibited content.

Use deterministic content rules for exact requirements such as “no word containing the letter a.” Semantic models can miss exact character constraints. Natural-language semantic instructions are suited to meaning-based restrictions; their results still require evaluation on your intended inputs.

Severity categories map `benign` to `0`, `suspicious` to `0.6`, and `malicious` to `1`. These are ordinal policy codes, not probabilities. Threshold `0.5` blocks suspicious and malicious content; `0.7` or `0.8` blocks the malicious category. Semantic inspection supplements authentication, access rules, privacy, signatures and budgets.

The explicit `config/policy.offline.yaml` profile disables semantic inspection. It provides local deterministic checks only; unmatched wording can pass. The `ollama` and `kev` providers remain available for their built-in security assessment. Historical `severity-v2` Ollama measurements in [testing](testing.md) are separate from Laya runtime results and do not establish accuracy for custom semantic instructions.

## Named Laya rules

Use **Policies → Add Laya rule** for meaning-based restrictions written in your own words. Each rule has an ID, instruction, direction and target. The console workflow is **Test with Laya → Review policy change → Review changes → Activate policy**, with an explicit confirmation before publication.

The configuration below is a `semantic` section to merge into a complete policy, preserving its models, tools, budgets and other controls. It is not a standalone policy file:

```yaml
semantic:
  provider: laya
  model: qwen3:4b
  threshold: 0.7
  timeout_ms: 30000
  scan_output: true
  rules:
    - id: no-personal-investment-advice
      instruction: >-
        Block personalized recommendations to buy or sell a specific investment.
        Allow general explanations of financial concepts.
      direction: input
      target: model
```

`direction` is `input`, `output` or `both`; `target` is `model`, `tool` or `all`. Only rules applicable to the current stage enter the assessment context. All applicable rules and global `semantic.instructions` share one model assessment per stage, alongside the built-in security rubric. The result is one severity classification; FastFence does not fabricate matched rule IDs from that score.

Limits are eight rules with unique IDs, 2,048 characters per nonblank instruction and 8,192 UTF-8 bytes for the combined rendered policy text. Named rules require provider `laya`. Any rule covering output also requires `scan_output: true`; incompatible configurations are rejected.

The editor tests a candidate against one sample using actual Laya, without saving the policy or executing a protected model/tool call. The displayed scope is input when the rule covers both directions, and model when it covers all targets. To test another combination, use [the management preview API](integration-reference.md#test-a-named-laya-rule). The candidate is assessed alongside current applicable rules; a block cannot be attributed to that rule alone, and a non-block does not test the full gateway pipeline.

After testing, inspect the policy diff and explicitly activate. Editing the rule or sample invalidates its test; stale policy versions and provider failures require a new review. Rule inventory actions support editing and removal. Remote configuration sources remain read-only through local management writes.

### Choose the correct rule editor

| Editor | What is stored | Request-time behavior |
| --- | --- | --- |
| **Add Laya rule** | A named natural-language instruction with direction and target | Actual semantic model assessment at applicable stages |
| **Add content rule** | A literal `contains`, `word_contains` or `equals` predicate | Deterministic local matching without inference |
| **Describe a fast rule** | A reviewed bounded configuration proposal produced by Laya | The resulting configured controls; generated literal predicates match locally |

Use **Add content rule** for exact words or letters, and **Add Laya rule** for meaning-based restrictions. The model can miss exact character constraints. Laya authoring does not turn arbitrary prose into a guaranteed fast predicate.

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

In **Policies**, select **Add content rule**, set its scope and samples, then preview, review and activate the rule. Preview evaluates only the candidate predicate: `NO MATCH` is not a promise that all other security controls will allow the request. Activation adds the rule to the current policy with a new version. Duplicate IDs, invalid rules and version conflicts are rejected. A remote configuration source must be updated at that source.

Management clients can retrieve `GET /api/admin/rules/schema`, then call `POST /api/admin/rules/preview` with a `rule` object and up to 16 `samples`, each at most 4,096 characters. Preview neither changes policy nor invokes a model. Publish a validated proposal through the existing versioned `PUT /api/admin/policy` endpoint.

## Describe a policy in the dashboard

Install the pinned Laya engine once with `integrations/laya/setup.sh`, start Ollama with `qwen3:4b` installed, and connect the console with your management identity. In **Policies**, choose **Describe a fast rule**:

1. Write a specific instruction in Polish or English and select **Draft with Laya**.
2. Inspect the before/after changes and exact operations. Drafting does not activate anything.
3. Enter examples, choose input/output and model/tool scope, and select **Test examples**.
4. Confirm that you reviewed the changes and results, then select **Activate this proposal**.
5. Open **Test requests** to try the policy against a real protected completion. Business-tool calls require separately registered handlers; the default product has no simulated business tools. The result includes the audit request ID and whether upstream execution occurred.

Supported instructions include blocking words containing `a`, redacting email addresses, blocking personal data and secrets, and restricting an existing tool to a subset of its already permitted roles. Selective detectors currently cover email and the eleven-digit Polish identifier heuristic. General compliance statements, new tools, role widening and arbitrary executable rules are rejected rather than silently invented.

For example, selective email redaction changes `privacy.detector_actions.pii_email`, leaving other detectors on their existing actions. A request containing both an email and a secret still blocks if the secret detector remains configured to block. Broad privacy instructions change all privacy controls for the requested direction and clear that direction's selective overrides. Any enabling of previously disabled privacy controls is disclosed in the proposed changes.

A proposal is bound to its management identity and original policy version, expires after ten minutes, and can be activated once. The server requires a preview before activation. Editing examples invalidates the browser's review state; editing the instruction discards the draft. Activation publishes the exact stored candidate without another model call. Preview checks local content controls only: role authorization, budget limits, semantic assessment and upstream behavior still run on an actual invocation.

The management endpoints are `POST /api/admin/policies/draft`, `/preview` and `/activate`. Authoring inference uses a bounded isolated local Laya process outside the deterministic rule matcher. Runtime semantic inspection is a separate stage and may call a model on each inspected interaction. A deployment with a separate configuration root can point the trusted `FASTFENCE_AUTHORING_ROOT` setting at its Laya-enabled checkout. Paths and model endpoints cannot be supplied by browser users.

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

To remove or change a rule, use its **Edit rule** or **Remove…** action in **Policies**, review the candidate, and explicitly activate it. Advanced JSON editing is available under **Edit configuration**. Alternatively, update the configured central source with a higher version. Changes apply to subsequent invocations.
