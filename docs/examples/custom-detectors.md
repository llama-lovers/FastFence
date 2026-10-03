# Write custom Python text detectors

Add your own literal phrases and regular expressions with Python files that
extend detect-secrets. These detectors run together with FastFence's built-in
credential detectors on nested input and output values, including dictionary
keys. A match follows the active policy's privacy action: block or redact.

## Install and configure

After [installing FastFence](../getting-started.md), download the
[examples archive](../downloads/fastfence-examples.zip) and extract its files into
`examples/` in your installation directory. The complete example uses synthetic
values and needs no repository checkout:

```sh
fastfence init --anonymization
python examples/custom_detector.py
export FASTFENCE_SECRET_PLUGIN_FILES='["examples/custom_detector.py"]'
fastfence doctor
fastfence serve
```

Keep that environment variable in the terminal or service configuration used to
start FastFence. Paths resolve relative to `FASTFENCE_ROOT` (the working directory
by default). Restart after editing a plugin: already loaded source remains in
memory. The regular Laya/Ollama setup from the installation guide is still needed
for requests that pass input controls and reach a model.

The setting accepts at most eight local `.py` files with 32 detector classes in
total. Each file may contain up to 65,536 bytes by default; the operator may set
`FASTFENCE_SECRET_PLUGIN_MAX_FILE_BYTES` between 1,024 and 1,048,576. Classes need
unique names across all custom and built-in detectors. Invalid or missing plugins
stop startup; they are never silently skipped.

## Define literal and regex rules

`CompanyCodeDetector` matches `ACME-DEMO-1234` and the literal phrase
`PROJECT ORCHID INTERNAL`. Use `re.escape(...)` when a string should be treated
literally, including its punctuation. `InternalPhraseDetector` shows the base
interface for custom Python matching. Yield the exact nonempty substring to
remove, preserving its original case.

<!-- source: examples/docs/custom_detector.py -->

Regex detectors supply one to 32 compiled Python `re` patterns, each at most
8,192 characters long. Patterns that match the empty string are rejected.
FastFence masks the complete regex match, including when a pattern uses capture
groups. Base detectors yield exact matching substrings. A detector may yield at
most 4,096 candidates per text view; invalid results or exceptions reject the
request with a static detector-unavailable reason.

The extension follows the upstream
[BasePlugin and RegexBasedDetector interfaces](https://github.com/Yelp/detect-secrets/blob/v1.5.0/detect_secrets/plugins/base.py).
FastFence invokes `analyze_string` directly and does not call `verify` or the
library's global file-scanning pipeline.

## Choose input and output behavior

In your installation's `config/policy.yaml`, keep the other fields and set:

```yaml
privacy:
  enabled: true
  input: block
  output: redact
```

Increment the existing top-level `version` when updating a running gateway.
The management console can make this policy change too. These defaults reject
an input containing a custom match before the model call and replace custom
matches in model/tool output with `[REDACTED:detect_secrets]`. Swap either action
to `redact` or `block` as needed. These actions apply to all secret detectors;
custom detector-specific action overrides are not currently supported.

With the gateway running, use the downloaded client from a second terminal:

```sh
python examples/protected_request.py --prompt 'Please summarize ACME-DEMO-1234'
```

With input blocking enabled, expect `decision: blocked`,
`reason: input_sensitive_data`, `upstream_executed: false`, and the static finding
`detect_secrets_CompanyCodeDetector`. Input redaction instead removes the match
before later controls and business execution. Turning `privacy.enabled` off
turns off this privacy scan as well.

## Operator trust boundary

Plugin files are trusted executable Python, with the server process's privileges.
Review them like application code. Keep matching functions stateless, fast and
free of file/network access, logging, and side effects. Avoid regexes that can
backtrack excessively. File and candidate limits do not sandbox Python or impose
a hard execution timeout on arbitrary plugin code.

Only trusted startup settings select these files. HTTP requests, policy updates,
and remote configuration cannot upload or select executable plugins. FastFence
loads their source during startup and does not reread files during requests; it
never logs matched text itself. Plugin authors remain responsible for any I/O or
logging their own code performs.
