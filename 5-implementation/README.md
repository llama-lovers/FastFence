# 5. Implementation

This directory is a navigation and startup guide. The actual application remains
in [`src/fastfence`](../src/fastfence/), with dependencies and executable entry point
in [`pyproject.toml`](../pyproject.toml). No second implementation is maintained here.

## Run the published product

Use macOS or Linux with **uv, Python 3.12, Git and `sh`**, and an already running
local Ollama service. uv can provision the compatible Python interpreter. Choose an
empty working directory for this evaluation and run:

```sh
uv tool run --python 3.12 fastfence@1.0.7
```

No repository checkout or separate `init`/`serve` step is required. The first launch
creates configuration, credentials and an issuer keyring; prepares pinned Laya;
checks/downloads the configured assessor when missing; prepares OCR dependencies
and models; then starts the gateway. It can require network access and time for
first-time downloads. Fresh defaults use Qwen3:4b for assessment and protected
completion as separate calls. Existing valid settings and keys are preserved.

Open **http://127.0.0.1:8000** and select **Connection**:

- `state/credentials.json` contains `local-admin` for policy management and
  `local-agent` for protected requests. Keep both values private.
- Connect the matching identities. Tokens remain in dashboard page memory;
  management credentials cannot execute agent requests.
- In **Test requests**, select the allowlisted model and submit `Hello`.
  Read the decision, input/output semantic statuses and `upstream_executed`.
  Find the request ID in **Activity**. HTTP 200 alone is not an allow decision.

For startup diagnostics:

```sh
uv tool run --python 3.12 fastfence@1.0.7 doctor --full
```

The [installation guide](../docs/getting-started.md), [manual checks](../docs/manual-testing.md)
and [settings reference](../docs/settings.md) contain the longer operational steps.
Some historical instructions pin an older release; use **1.0.7** when reproducing
this submission. Component/configuration repairs may require restarting the gateway.

## Source map

| Area | Canonical source |
| --- | --- |
| Application composition and protocol mounts | [app/factory.py](../src/fastfence/app/factory.py) |
| One-command startup and provisioning | [CLI](../src/fastfence/app/interfaces/cli/) |
| Policy engine and bounded admission | [application/services](../src/fastfence/modules/control/application/services/) |
| Policy models, literal rules, semantic scopes | [domain](../src/fastfence/modules/control/domain/) |
| Atomic configuration snapshots and providers | [persistence/policy.py](../src/fastfence/modules/control/persistence/policy.py) |
| Actual Laya assessment | [persistence/laya_semantic.py](../src/fastfence/modules/control/persistence/laya_semantic.py) |
| OpenAI-compatible, ACP, documents and management HTTP | [HTTP adapters](../src/fastfence/app/interfaces/http/) |
| Authenticated MCP server | [MCP adapter](../src/fastfence/modules/control/interfaces/mcp/server.py) |
| Privacy tokens and key-based restoration | [anonymization module](../src/fastfence/modules/anonymization/) |
| Local OCR and protected document processing | [OCR module](../src/fastfence/modules/ocr/) and [workflow](../src/fastfence/workflows/document_markdown.py) |
| Package, lint and test configuration | [pyproject.toml](../pyproject.toml), [pre-commit](../.pre-commit-config.yaml), [GitHub Actions](../.github/workflows/) |

## Working integration examples

These are complete tracked programs with existing verification evidence, not new
pseudocode. Run them using each guide's dependency and credential setup. The product
ships no simulated business handlers; tool adapters must be explicitly connected
and allowlisted.

| Integration | Runnable code | Guide and actual evidence |
| --- | --- | --- |
| Protected REST completion | [protected_request.py](../examples/docs/protected_request.py) | [Guide](../docs/examples/protected-request.md), [recording](../presentation/output/demo-evidence.json) |
| OpenAI Python SDK | [openai_client.py](../examples/docs/openai_client.py) | [Guide](../docs/examples/openai-client.md), [actual installed-package SDK run](../presentation/output/integration-demo-evidence.json) |
| MCP client | [mcp_client.py](../examples/docs/mcp_client.py) | [Guide](../docs/examples/mcp-client.md), [actual MCP HTTP proof](../presentation/output/mcp-demo-evidence.json) |
| Protected FastMCP tool | [fastmcp_server.py](../examples/docs/fastmcp_server.py) | [Guide](../docs/examples/fastmcp-server.md), with [complete policy](../examples/docs/policy.yaml) |
| Agent Communication Protocol | [client](../examples/docs/acp_client.py), [gateway](../examples/docs/acp_gateway.py), [peer](../examples/docs/acp_server.py) | [Guide](../docs/examples/acp.md), [actual official-SDK proof](../presentation/output/acp-demo-evidence.json) |
| Reviewed natural-language policy | [semantic_policy.py](../examples/docs/semantic_policy.py) | [Guide](../docs/examples/semantic-policy.md), [eight-case recorded review](../presentation/output/demo-evidence.json) |
| RSA-backed reversible privacy | [asymmetric_keys.py](../examples/docs/asymmetric_keys.py) | [Guide](../docs/examples/asymmetric-anonymization.md), [actual restoration proof](../presentation/output/anonymization-demo-evidence.json) |
| Images and multipage PDF | [synthetic document fixtures](../examples/documents/) | [Manual OCR flow](../docs/manual-testing.md#images-and-multipage-pdfs), [recorded OCR evidence](../presentation/output/ocr-demo-evidence.json) |
| Additional secret detector | [custom_detector.py](../examples/docs/custom_detector.py) | [Guide](../docs/examples/custom-detectors.md) |

Endpoints: REST `/api/models/complete`, OpenAI-compatible `/v1`, MCP `/mcp/`, ACP
`/acp`. Agents use bearer credentials. ACP is **Agent Communication Protocol**:
synchronous stateless text with server-configured peers, not Agent Client Protocol
or a claim of complete A2A support. Its official SDK example uses a separate pinned
environment; follow the guide rather than downgrading product dependencies.

The [integration reference](../docs/integration-reference.md) defines the supported
request/response boundaries. The [OpenAI upstream guide](../docs/examples/openai-upstream.md)
explains how to change the business provider independently from Laya assessment.

## Configuration and deployment scope

The central policy/feed control each protected invocation. Valid versioned policy
changes hot-reload; `.env` startup changes require restart. Invalid configuration
keeps the last valid snapshot. A missing business adapter or unavailable required
semantic assessor fails closed.

This submission targets a **complete local process**. Budget counters and retained
audit are in memory and reset on restart. Multiple processes do not share a global
quota. Repeat initialization preserves valid policy, credentials and keys; this
is setup idempotency, not exactly-once business execution.

Reversible privacy requires configured issuer and recipient keys. In the verified
RSA setup, the gateway loads both public and private recipient keys. It embeds the
encrypted original in a token rather than storing a conversation mapping database.
Restoration requires an intact token, authorization and the explicit switch.
The OCR path produces protected text; it does not produce an edited PDF.

## Review the submitted result

- [Exactly 10 slides, PDF](../presentation/output/fastfence-submission.pdf) and
  [editable PowerPoint](../presentation/output/fastfence-submission.pptx).
- [Recorded product demo](../presentation/output/fastfence-submission.mp4), with real
  SDK/MCP/ACP/privacy/document evidence linked above.
- [Apache 2.0 license](../LICENSE), [specifications](../specs/changes/) and
  [tests](../tests/).
