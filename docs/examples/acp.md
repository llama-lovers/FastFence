# Protect agent-to-agent calls with ACP

FastFence accepts **Agent Communication Protocol** requests and forwards them to
a configured peer agent through the existing tool policy engine:

```text
ACP client → FastFence /acp/runs → input controls → trusted ACP peer
                                                     ↓
ACP response ← output controls ← completed peer response
```

This is the IBM/BeeAI REST protocol, separate from Agent Client Protocol for
editors. Its [official repository](https://github.com/i-am-bee/acp) is archived and
[the project moved into A2A](https://agentcommunicationprotocol.dev/introduction/welcome).
FastFence implements a bounded compatibility profile: synchronous, stateless,
inline plain-text runs and authenticated agent discovery. It does not claim full
ACP or A2A conformance.

## Run a real peer agent locally

Install FastFence **1.0.0 or later** using [Getting started](../getting-started.md),
then extract the [complete examples archive](../downloads/fastfence-examples.zip)
into `examples/`. Run all commands from the installation directory. Keep the
gateway in its own `uv run` FastFence environment. Create a separate environment
for the archived SDK peer and client; its Uvicorn pin does not change your gateway.
The SDK also imports `requests` without declaring that dependency, so install it
explicitly in this separate environment:

```sh
uv venv --python 3.12 .acp-venv
uv pip install --python .acp-venv/bin/python 'acp-sdk==1.0.3' 'uvicorn==0.35.0' 'requests==2.34.2'
.acp-venv/bin/python examples/acp_server.py
```

The official ACP SDK serves an actual uppercase operation on loopback port 8020.
It generates a separate private backend credential in
`state/examples/acp-upstream-token.txt`. All backend endpoints require that
credential. The file's contents are never printed.

In a second terminal, run the gateway with its own FastFence dependencies:

```sh
uv run --python 3.12 --no-project --with fastfence==1.0.1 python examples/acp_gateway.py
```

This starts an isolated FastFence instance on port 8030 and registers the
`uppercase` peer as policy tool `acp.uppercase`. Its configuration and gateway
credentials live under `state/examples/acp-gateway/`. It preserves existing
configuration on restart and does not edit your main installation. The explicit
example policy uses deterministic checks so no model is needed; the default
product policy still requires Laya.

In a third terminal, use the **official ACP SDK client**:

```sh
.acp-venv/bin/python examples/acp_client.py --prompt 'hello'
.acp-venv/bin/python examples/acp_client.py --prompt 'forbidden'
.acp-venv/bin/python examples/acp_client.py --prompt 'email@example.org'
```

Expected: `hello` completes with `HELLO`; `forbidden` returns a failed run before
the peer executes and the script exits 1; the email is redacted before forwarding.
HTTP 200 can contain a failed run: check `status`, `error.data.reason` and
`error.data.upstream_executed`. Successful output is returned only after output
controls pass. Use **Activity** at <http://127.0.0.1:8030> to inspect the decision.
The ACP run UUID corresponds to the audit request ID without UUID hyphens.

Server and gateway accept `--port`; the gateway also accepts `--upstream-url`.
The client accepts `--url`, `--agent` and `--credentials`. Its default credential
is the isolated example's `local-agent`; management credentials cannot invoke ACP.

## Connect your existing ACP agent

Configure trusted startup settings in the gateway's environment or private `.env`:

```sh
export FASTFENCE_ACP_AGENTS='{"assistant":{"base_url":"https://peer.example.org","agent_name":"assistant"}}'
```

Replace the example URL and agent name with your own peer. Add `api_key` inside
that trusted configuration if the peer requires bearer authentication. This is
the backend credential, separate from callers' FastFence tokens. It is not
returned by discovery or policy APIs. Remote peers require HTTPS; HTTP is accepted
only for loopback. Caller input cannot choose upstream URLs or credentials.

Add the corresponding tool to `config/policy.yaml`, preserving other settings and
incrementing the active policy version:

```yaml
tools:
  acp.assistant:
    roles: [analyst]
    timeout_ms: 30000
    cost_microusd: 1
```

Restart after changing startup settings. Policy changes still hot-reload. With
your normal gateway running on port 8000:

```sh
.acp-venv/bin/python examples/acp_client.py --url http://127.0.0.1:8000 \
  --credentials state/credentials.json --agent assistant --prompt 'Hello'
```

`GET /acp/agents` exposes only registered, configured, role-allowed agents.
`POST /acp/runs` accepts the same bearer identity used by REST/MCP; all these
transports share that subject's policy and in-memory budget. Peer costs are the
configured tool cost and bounded text resource accounting, not provider billing
token measurements. Direct backend access must remain restricted to trusted
gateway credentials or network boundaries.
These controls cover messages crossing FastFence. They do not inspect a remote
agent's internal model/tool calls unless those calls also pass through FastFence;
hidden internal token usage is not measured by this adapter.

## Supported content and execution

- Only `mode: sync`, inline `text/plain`, and `content_encoding: plain` are
  accepted. Binary/base64 parts, remote content URLs, non-null metadata, caller-selected sessions,
  asynchronous jobs, streaming, polling, resume and remote cancellation are
  rejected explicitly. The gateway does not fetch attachments or persist runs.
- Input bodies are bounded to 65,536 bytes; message and part counts and text
  lengths are bounded separately. Unsupported fields are rejected before execution.
- Role labels and valid SDK timestamps are transport metadata. Named roles such
  as `agent/researcher` normalize to `agent`; timestamps are discarded. Only text
  and numeric role markers enter tool controls, so a forbidden letter in
  `text/plain` cannot accidentally block unrelated text. Claimed roles never
  authenticate a caller.
- The whole peer response is buffered within a size limit and checked before
  delivery. A failed output check cannot undo work already performed by the peer.
  Timeouts fail closed and consume conservative reserved resources; ending the
  local request cannot guarantee that a remote agent stops its own work.
- Stateless clients should send any necessary conversation text explicitly on
  each run. FastFence maintains no ACP conversation or result store. The example
  SDK backend creates its own session even when none is requested. FastFence validates and discards the returned UUID: it never returns, retains or reuses that session identifier. The peer may retain its own state independently of the stateless gateway.

The raw protected tool representation, also available through REST/MCP, is
`{"tool":"acp.assistant","arguments":{"input":[{"role":0,"parts":["Hello"]}]}}`.
Role `0` means user and `1` means agent. This internal text projection differs from
the native ACP wire schema. Literal and semantic rules use target **Tools**.

The [official OpenAPI](https://github.com/i-am-bee/acp/blob/main/docs/spec/openapi.yaml)
and [SDK client](https://github.com/i-am-bee/acp/blob/main/python/src/acp_sdk/client/client.py)
define the wire messages and `run_sync` behavior used by these examples.

## Complete example sources

### Official SDK peer

<!-- source: examples/docs/acp_server.py -->

### Gateway registration

<!-- source: examples/docs/acp_gateway.py -->

### Official SDK client

<!-- source: examples/docs/acp_client.py -->

### Isolated policy

<!-- source: examples/docs/acp_policy.yaml -->
