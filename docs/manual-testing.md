# Manual acceptance test

Run from the `HackYeah2026-challenge-second` repository. Your existing private
credentials stay in `state/demo-tokens.json`. Never put them into a policy file.

## Start and connect

```sh
uv sync --locked
uv run fastfence serve
```

Open <http://127.0.0.1:8000>. Click **Connect identities**, then copy
`analyst-blue` and `security-admin` from your local `state/demo-tokens.json` into
the matching fields. Tokens stay in page memory. Reloading the page clears them.
If this is a fresh checkout, run `uv run fastfence init` once first.

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

A private 32-byte keyring must be configured as
`FASTFENCE_ANONYMIZATION_KEYS_JSON` in `.env`, with active key ID
`FASTFENCE_ANONYMIZATION_KEY_ID` (default `local-v1`). These are symmetric encryption
keys, not a public/private key pair. The local development setup has its own
private key; keys are never committed or returned by the dashboard.

## Images and multipage PDFs

The local development setup uses an isolated OCR interpreter and downloaded
models configured through `FASTFENCE_OCR_PYTHON` and `FASTFENCE_OCR_MODELS` in `.env`.
Fresh OCR setup:

```sh
uv venv state/private/ocr-env --python 3.12
uv pip install --python state/private/ocr-env/bin/python \
  paddlepaddle==3.3.0 paddleocr==3.4.0 pypdfium2==5.13.0 pillow==12.3.0 pydantic==2.12.5
PYTHONPATH=src state/private/ocr-env/bin/python \
  -m fastfence.modules.ocr.persistence.bootstrap state/private/ocr-models
```

Set the two OCR settings to the absolute paths of that interpreter and model
directory; restart the gateway after changing startup settings.

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
