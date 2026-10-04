"""Isolated official ACP peer and FastFence service setup for the demo."""

import hashlib
import json
import socket
import threading
import time


def start_server(app, servers):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="error", access_log=False)
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    servers.append((server, thread, sock))
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("Isolated service did not start")
        time.sleep(0.05)
    return base


def peer_app(token, calls):
    import hmac

    from acp_sdk.models import Message, MessagePart
    from acp_sdk.server import Server
    from acp_sdk.server.app import create_app
    from fastapi.responses import JSONResponse

    server = Server()

    @server.agent(
        name="uppercase",
        input_content_types=["text/plain"],
        output_content_types=["text/plain"],
    )
    async def uppercase(input: list[Message]):
        """Uppercase actual text using a deterministic local example agent."""
        calls.append(1)
        for message in input:
            yield Message(
                role="agent/uppercase",
                parts=[
                    MessagePart(content=part.content.upper())
                    for part in message.parts
                ],
            )

    app = create_app(*server.agents, enable_playground_cors=False)

    @app.middleware("http")
    async def authenticate(request, call_next):
        if not hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token
        ):
            return JSONResponse({"code": "unauthorized"}, status_code=401)
        return await call_next(request)

    return app


def gateway_app(root, peer_url, peer_token, tokens):
    from fastfence.app.factory import create_app
    from fastfence.shared.acp import ACPAgentSettings
    from fastfence.shared.settings.app_settings import AppSettings

    config = root / "config"
    config.mkdir(parents=True)
    policy = {
        "version": 1,
        "description": "Isolated official ACP SDK demonstration",
        "privacy": {"enabled": True, "input": "redact", "output": "redact"},
        "signatures_enabled": True,
        "semantic": {"provider": "disabled"},
        "tools": {
            "acp.uppercase": {
                "roles": ["demo"],
                "timeout_ms": 30000,
                "cost_microusd": 1,
            }
        },
        "models": {},
        "text_rules": [],
        "budgets": {
            "demo": {
                "calls": 100,
                "tokens": 1000000,
                "compute_ms": 1000000,
                "cost_microusd": 1000000,
                "concurrent": 2,
            }
        },
    }
    (config / "policy.yaml").write_text(json.dumps(policy))
    (config / "signatures.json").write_text(
        json.dumps({"version": 1, "signatures": []})
    )
    identities = [
        {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "identity": {
                "subject": name,
                "tenant": "acp-demo",
                "roles": ["demo"],
                "admin": name == "admin",
            },
        }
        for name, token in tokens.items()
    ]
    return create_app(
        AppSettings(
            root=root,
            identity_config_json=json.dumps(identities),
            acp_agents={
                "uppercase": ACPAgentSettings(
                    base_url=peer_url,
                    agent_name="uppercase",
                    api_key=peer_token,
                )
            },
        )
    )
