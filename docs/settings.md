# Configuration

Here you can find all available configuration options using ENV variables.

## AppSettings

**Environment Prefix**: `FASTFENCE_`

| Name                                  | Type                     | Default                       | Description                                                                                      | Example                       |
|---------------------------------------|--------------------------|-------------------------------|--------------------------------------------------------------------------------------------------|-------------------------------|
| `FASTFENCE_ROOT`                      | `Path`                   | `"<project_dir>"`             | Repository/config root                                                                           | `"<project_dir>"`             |
| `FASTFENCE_STATE`                     | `Path` \| `null`         | `null`                        | Legacy private startup identity configuration directory                                          | `null`                        |
| `FASTFENCE_AUTHORING_ROOT`            | `Path` \| `null`         | `null`                        | Trusted repository root for the isolated Laya authoring installation                             | `null`                        |
| `FASTFENCE_IDENTITY_CONFIG_JSON`      | `string` \| `null`       | `null`                        | Trusted startup identity records as JSON                                                         | `null`                        |
| `FASTFENCE_IDENTITY_CONFIG_FILE`      | `Path` \| `null`         | `null`                        | Trusted read-only startup identity configuration file                                            | `null`                        |
| `FASTFENCE_INSTANCE_ID`               | `string` \| `null`       | `null`                        | Trusted instance label; generated once when omitted                                              | `null`                        |
| `FASTFENCE_AUDIT_LIMIT`               | `integer`                | `10000`                       | Maximum sanitized audit records retained in memory                                               | `10000`                       |
| `FASTFENCE_CONFIG_URL`                | `string` \| `null`       | `null`                        | Trusted HTTP source for coherent policy/feed JSON bundle                                         | `null`                        |
| `FASTFENCE_CONFIG_POLL_INTERVAL`      | `number`                 | `2.0`                         | Background configuration polling interval in seconds                                             | `2.0`                         |
| `FASTFENCE_CONFIG_FETCH_TIMEOUT`      | `number`                 | `5.0`                         | Configuration source fetch timeout in seconds                                                    | `5.0`                         |
| `FASTFENCE_MAX_CONFIG_SOURCE_BYTES`   | `integer`                | `262144`                      | Maximum configuration source size in bytes                                                       | `262144`                      |
| `FASTFENCE_OLLAMA_URL`                | `string`                 | `"http://127.0.0.1:11434"`    | Trusted Ollama endpoint                                                                          | `"http://127.0.0.1:11434"`    |
| `FASTFENCE_MODEL_PROVIDER`            | `"ollama"` \| `"openai"` | `"ollama"`                    | Protected business model backend                                                                 | `"ollama"`                    |
| `FASTFENCE_OPENAI_BASE_URL`           | `string`                 | `"http://127.0.0.1:11434/v1"` | Trusted OpenAI-compatible base URL including /v1; HTTPS or loopback HTTP                         | `"http://127.0.0.1:11434/v1"` |
| `FASTFENCE_OPENAI_API_KEY`            | `string` \| `null`       | `null`                        | Server-only upstream bearer credential; independent of gateway caller tokens                     | `null`                        |
| `FASTFENCE_KEV_URL`                   | `string`                 | `"http://127.0.0.1:8009"`     | Trusted Kev endpoint                                                                             | `"http://127.0.0.1:8009"`     |
| `FASTFENCE_ANONYMIZATION_KEYS_JSON`   | `string` \| `null`       | `null`                        | Private JSON keyring: key ID to base64-encoded 32-byte key; required for stateless anonymization | `null`                        |
| `FASTFENCE_ANONYMIZATION_KEYS_FILE`   | `Path` \| `null`         | `null`                        | Private JSON keyring file; defaults to state/anonymization-keys.json when present                | `null`                        |
| `FASTFENCE_ANONYMIZATION_KEY_ID`      | `string`                 | `"local-v1"`                  | Active key ID for issuing stateless anonymization tokens                                         | `"local-v1"`                  |
| `FASTFENCE_ANONYMIZATION_TTL_SECONDS` | `integer`                | `1800`                        | Maximum lifetime of reversible text tokens in seconds                                            | `1800`                        |
| `FASTFENCE_OCR_PYTHON`                | `Path` \| `null`         | `null`                        | Trusted isolated OCR Python interpreter                                                          | `null`                        |
| `FASTFENCE_OCR_MODELS`                | `Path` \| `null`         | `null`                        | Trusted local OCR model directory                                                                | `null`                        |
| `FASTFENCE_OCR_TIMEOUT_SECONDS`       | `number`                 | `60`                          | OCR worker timeout in seconds                                                                    | `60`                          |
| `FASTFENCE_OCR_MAX_PAGES`             | `integer`                | `10`                          | Maximum document pages; excess pages are rejected                                                | `10`                          |
| `FASTFENCE_OCR_MAX_PIXELS`            | `integer`                | `20000000`                    | Maximum pixels per OCR page                                                                      | `20000000`                    |
| `FASTFENCE_OCR_MAX_TOTAL_PIXELS`      | `integer`                | `80000000`                    | Maximum aggregate pixels per OCR request                                                         | `80000000`                    |
