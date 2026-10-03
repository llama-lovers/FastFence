# Configuration

Here you can find all available configuration options using ENV variables.

## AppSettings

**Environment Prefix**: `FASTFENCE_`

| Name                   | Type             | Default                    | Description                             | Example                    |
|------------------------|------------------|----------------------------|-----------------------------------------|----------------------------|
| `FASTFENCE_ROOT`       | `Path`           | `"<project_dir>"`          | Repository/config root                  | `"<project_dir>"`          |
| `FASTFENCE_STATE`      | `Path` \| `null` | `null`                     | Private credential and ledger directory | `null`                     |
| `FASTFENCE_OLLAMA_URL` | `string`         | `"http://127.0.0.1:11434"` | Trusted Ollama endpoint                 | `"http://127.0.0.1:11434"` |
| `FASTFENCE_KEV_URL`    | `string`         | `"http://127.0.0.1:8009"`  | Trusted Kev endpoint                    | `"http://127.0.0.1:8009"`  |
