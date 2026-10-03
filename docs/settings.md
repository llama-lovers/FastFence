# Configuration

Here you can find all available configuration options using ENV variables.

## AppSettings

**Environment Prefix**: `FASTFENCE_`

| Name                                | Type               | Default                    | Description                                                          | Example                    |
|-------------------------------------|--------------------|----------------------------|----------------------------------------------------------------------|----------------------------|
| `FASTFENCE_ROOT`                    | `Path`             | `"<project_dir>"`          | Repository/config root                                               | `"<project_dir>"`          |
| `FASTFENCE_STATE`                   | `Path` \| `null`   | `null`                     | Legacy private startup identity configuration directory              | `null`                     |
| `FASTFENCE_AUTHORING_ROOT`          | `Path` \| `null`   | `null`                     | Trusted repository root for the isolated Laya authoring installation | `null`                     |
| `FASTFENCE_IDENTITY_CONFIG_JSON`    | `string` \| `null` | `null`                     | Trusted startup identity records as JSON                             | `null`                     |
| `FASTFENCE_IDENTITY_CONFIG_FILE`    | `Path` \| `null`   | `null`                     | Trusted read-only startup identity configuration file                | `null`                     |
| `FASTFENCE_INSTANCE_ID`             | `string` \| `null` | `null`                     | Trusted instance label; generated once when omitted                  | `null`                     |
| `FASTFENCE_AUDIT_LIMIT`             | `integer`          | `10000`                    | Maximum sanitized audit records retained in memory                   | `10000`                    |
| `FASTFENCE_CONFIG_URL`              | `string` \| `null` | `null`                     | Trusted HTTP source for coherent policy/feed JSON bundle             | `null`                     |
| `FASTFENCE_CONFIG_POLL_INTERVAL`    | `number`           | `2.0`                      | Background configuration polling interval in seconds                 | `2.0`                      |
| `FASTFENCE_CONFIG_FETCH_TIMEOUT`    | `number`           | `5.0`                      | Configuration source fetch timeout in seconds                        | `5.0`                      |
| `FASTFENCE_MAX_CONFIG_SOURCE_BYTES` | `integer`          | `262144`                   | Maximum configuration source size in bytes                           | `262144`                   |
| `FASTFENCE_OLLAMA_URL`              | `string`           | `"http://127.0.0.1:11434"` | Trusted Ollama endpoint                                              | `"http://127.0.0.1:11434"` |
| `FASTFENCE_KEV_URL`                 | `string`           | `"http://127.0.0.1:8009"`  | Trusted Kev endpoint                                                 | `"http://127.0.0.1:8009"`  |
