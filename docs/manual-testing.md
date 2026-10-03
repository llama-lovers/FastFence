# Manual acceptance test

## Install from a fresh clone

Prerequisites: Git, Python 3.12, [uv](https://docs.astral.sh/uv/), and
[Ollama](https://ollama.com/) for the model features. Start the Ollama application
(or run `ollama serve` in a separate terminal). The steps below create new local
credentials and encryption keys; they do not depend on the maintainer's `.env`
or private state.

```sh
git clone https://github.com/llama-lovers/HackYeah2026-challenge-second.git
cd HackYeah2026-challenge-second
uv sync --locked
uv run fastfence init --anonymization
sh integrations/laya/setup.sh
sh scripts/setup-ocr.sh
ollama pull qwen3:4b
ollama pull qwen3:0.6b
uv run fastfence doctor --full
uv run fastfence serve
```

**Wait for `doctor --full` to pass before starting the scenarios below.** It
checks the core configuration, private keyring, Laya environment, OCR interpreter
and models, and both Qwen models. It prints the setup command for any missing
prerequisite. Model downloads require an internet connection; OCR inference
uses only the downloaded local files.

`init --anonymization` creates `state/identities.json`, `state/demo-tokens.json`
and `state/anonymization-keys.json` with private permissions. Repeating it
preserves existing valid credentials and keys. Keep these files out of Git.
The startup reads the keyring automatically, and detects the OCR environment
created by `scripts/setup-ocr.sh`. No manually invented absolute paths or copied
private `.env` are required for this setup.

If you want to verify core controls first, run only `uv sync --locked`,
`uv run fastfence init --anonymization`, `uv run fastfence doctor`, then
`uv run fastfence serve`. Laya, model completion and OCR need the full setup above.

## Connect

Open <http://127.0.0.1:8000>. Click **Connect identities**, then copy
`analyst-blue` and `security-admin` from your own `state/demo-tokens.json` into
the matching fields. Tokens stay in page memory. Reloading the page clears them.

If another gateway already uses port 8000, stop that instance or use
`uv run fastfence serve --port 8002` and open <http://127.0.0.1:8002>.
Use the selected port in MCP/client URLs too.

Run automatic checks separately:

```sh
uv run pytest -q
uv run pre-commit run --all-files
```

## A rule in your own words

1. Click **Describe a policy**.
2. Enter: `Block model input containing any word with the letter a, case insensitive. Do not change output rules.`
3. Generate the proposal with Laya. Inspect the operations and YAML diff.
4. Review the generated test cases and their expected results. Preview the same
   examples against the current and proposed configuration.
5. Activate only when your intended cases pass. A failed regression prevents activation.
6. In the playground choose **Local Qwen model**. `Cat` must be blocked with
   `upstream not executed`; `Hi` may reach the allowlisted model.

The rule is compiled to local deterministic checks. Laya drafts the policy;
it is not called on every protected request. If Qwen is unavailable, allowed
input ends in `model_unavailable_fail_closed`; blocked input still needs no model.
The activated policy lives in `config/policy.yaml`; reviewed regression cases
are stored separately in `config/policy-tests.yaml`.

## Stateless anonymization and optional restoration

First remove the letter-a rule: it would intentionally block many names and
email addresses before anonymization. Use **Manage policy** to increase `version`
and add this configuration, keeping your tools, models and budgets:

```yaml
privacy:
  enabled: true
  input: redact
  output: redact
anonymization:
  enabled: true
  mode: reversible
  rules:
    - id: demo-person
      operator: literal
      value: Anna Kowalska
      replacement: PERSON
      direction: both
      target: all
      allow_restore: true
```

The manager accepts JSON; the corresponding fragment is:

```json
"anonymization": {
  "enabled": true,
  "mode": "reversible",
  "rules": [{"id":"demo-person","operator":"literal","value":"Anna Kowalska",
    "replacement":"PERSON","direction":"both","target":"all","allow_restore":true}]
}
```

Set `privacy.input` to `redact` when testing email patterns. Explicit privacy
`block` always wins over anonymization.

Use **Business tool → knowledge.search** with
`{"query":"Anna Kowalska"}`. The demo tool echoes the protected query, making this
a deterministic restoration test without depending on model behavior:

- **Restore originals** off: the response contains a `PERSON` token, not the name.
- **Restore originals** on: the response can contain the original name.
- Set `allow_restore: false` and increment policy version: restoration is denied.
- Set `mode: irreversible`: aliases carry no recoverable original; restoration is denied.

Try the same through Qwen with `Repeat this text exactly: Anna Kowalska`.
Restoration requires the entire valid token to survive generation. A model may
shorten or alter it; the gateway never guesses missing originals.

There is no conversation store or mapping database. Stable opaque IDs identify
equal values within the trusted owner/rule scope. Reversible tokens carry
AEAD-encrypted originals and expire; randomized full tokens can differ between
requests while their stable IDs remain equal. Changing rule text, losing the
key, expiration or using another identity prevents recovery.

`init --anonymization` provisions the private 32-byte keyring automatically.
For a managed installation, use `FASTFENCE_ANONYMIZATION_KEYS_FILE` or
`FASTFENCE_ANONYMIZATION_KEYS_JSON`, with active key ID
`FASTFENCE_ANONYMIZATION_KEY_ID` (default `local-v1`). Do not set both explicit
key sources. Environment JSON overrides the automatically discovered default
file. These are symmetric encryption keys; keep and back them up privately.
Keys are never returned by the dashboard.

## Images and multipage PDFs

The full installation above already prepares OCR. To add it later:

```sh
sh scripts/setup-ocr.sh
uv run fastfence doctor --full
```

Restart the gateway after installing OCR or changing startup settings. The
installer uses the locked `ocr` dependency extra in a separate environment and
preloads the model files. Advanced deployments can set `FASTFENCE_OCR_PYTHON`
and `FASTFENCE_OCR_MODELS`; preserve the virtual environment interpreter path
rather than resolving its symlink to the base Python.

1. Choose `examples/documents/two-pages.pdf` in **Document → protected Markdown**.
2. Choose **Inspect and export Markdown**, then **Process document**.
3. With input privacy set to `redact`, expect ordered page sections and removed
   matching sensitive data. Download the same approved content with **Download approved .md**.
4. Choose **Inspect and send Markdown to model** to run the approved text through
   the allowlisted Qwen model. Only the sanitized Markdown reaches the model.
5. Change privacy input to `block`; a detected sensitive value must prevent both
   Markdown delivery and model execution.

OCR is approximate: inspect the extraction on your documents, especially small,
rotated or low-contrast text. The application replaces attachments with Markdown;
it does not edit source image/PDF pixels or produce a redacted PDF.

## Try it through MCP

With the gateway running and your policy activated, run this from the repository:

```sh
uv run python - <<'PYCODE'
import asyncio
import json
from pathlib import Path
from fastmcp import Client
from fastmcp.client.auth import BearerAuth

async def main():
    token = json.loads(Path("state/demo-tokens.json").read_text())["analyst-blue"]
    async with Client("http://127.0.0.1:8000/mcp/", auth=BearerAuth(token)) as client:
        for restore in (False, True):
            result = await client.call_tool("invoke", {
                "tool": "knowledge.search",
                "arguments": {"query": "Anna Kowalska"},
                "restore_originals": restore,
            })
            print(result.data)

asyncio.run(main())
PYCODE
```

This uses the reversible person rule above. For the letter-a rule, call the MCP
`complete` tool with `{"model":"qwen3:0.6b","prompt":"Cat","max_output_tokens":16}`
and expect an input block before Qwen executes.

## Check the evidence

Use **View this decision in audit** on a result. Compare policy/feed version,
decision, findings and whether upstream executed. Audit contains metadata only;
it must not contain prompts, OCR text, original names or recovery tokens.
The local suite is reproducible without downloading OCR weights or calling Qwen;
real-model and real-OCR checks are separate from offline CI.

## Reproduce the clean-install acceptance check

This creates a new clone of the committed source, strips inherited FastFence
settings, creates a fresh virtual environment and new private state, and starts
a gateway on a free local port. It does not modify the configuration or
credentials of your working checkout.

```sh
# No model service required; this also runs in GitHub Actions.
uv run python scripts/smoke_clean_install.py

# Installs isolated Laya/OCR, pulls models, and tests the real feature paths.
# Requires a running Ollama service.
uv run python scripts/smoke_clean_install.py --full
```

Public package/model download caches may be reused. Existing FastFence keys,
credentials, `.env`, feature installations and policy edits are never copied.
