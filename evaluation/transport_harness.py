"""Real isolated gateway process and authenticated HTTP/JSON-RPC MCP clients."""

from __future__ import annotations

import io
import itertools
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

import httpx
import yaml
from pydantic import BaseModel, Field

from fastfence.app.interfaces.cli.main import initialize
from fastfence.modules.control.domain.models import Policy


class Gateway(BaseModel):
    url: str
    tokens: dict[str, str] = Field(exclude=True, repr=False)
    rules: int


def configuration(root: Path, rules: int) -> None:
    policy = yaml.safe_load(Path("config/policy.offline.yaml").read_text())
    assert policy["semantic"]["provider"] == "disabled"
    policy["text_rules"] = [
        {
            "id": f"benchmark-{index:02}",
            "operator": "contains",
            "value": f"blocked-marker-{index:02}",
            "direction": "both",
            "target": "tool",
            "action": "block",
            "case_sensitive": False,
        }
        for index in range(rules)
    ]
    for budget in policy["budgets"].values():
        budget.update(
            calls=1_000_000,
            tokens=100_000_000,
            cost_microusd=1_000_000_000,
            compute_ms=1_000_000_000,
            concurrent=16,
        )
    Policy.model_validate(policy)
    (root / "config").mkdir()
    (root / "config/policy.yaml").write_text(yaml.safe_dump(policy))
    (root / "config/signatures.json").write_text(
        Path("config/signatures.json").read_text()
    )
    with redirect_stdout(io.StringIO()):
        initialize(root / "state")


@contextmanager
def isolated_gateway(rules: int) -> Iterator[Gateway]:
    with TemporaryDirectory(prefix="fastfence-transport-") as temporary:
        root = Path(temporary)
        configuration(root, rules)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("FASTFENCE_")
        }
        env.update(
            FASTFENCE_ROOT=str(root),
            FASTFENCE_STATE=str(root / "state"),
            FASTFENCE_INSTANCE_ID=f"transport-{rules}-rules",
            FASTFENCE_AUDIT_LIMIT="10000",
            FASTFENCE_CONFIG_POLL_INTERVAL="300",
        )
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "fastfence.app.factory:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        gateway = Gateway(
            url=f"http://127.0.0.1:{port}",
            tokens=json.loads((root / "state/demo-tokens.json").read_text()),
            rules=rules,
        )
        try:
            with httpx.Client(
                base_url=gateway.url, trust_env=False, timeout=1
            ) as client:
                for _ in range(150):
                    if server.poll() is not None:
                        raise RuntimeError("Isolated gateway failed to start")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(
                        "Isolated gateway startup deadline exceeded"
                    )
            yield gateway
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


class Transport:
    def __init__(
        self, client: httpx.AsyncClient, protocol: Literal["http", "mcp"]
    ) -> None:
        self.client, self.protocol = client, protocol
        self.identifiers = itertools.count(1)

    async def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": next(self.identifiers),
                "method": method,
                "params": params,
            },
        )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            raise RuntimeError("MCP protocol error invalidates benchmark")
        return result["result"]

    async def initialize(self) -> None:
        if self.protocol == "mcp":
            await self.rpc(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "fastfence-transport-benchmark",
                        "version": "1",
                    },
                },
            )
            response = await self.client.post(
                "/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
            )
            if response.status_code not in {200, 202, 204}:
                raise RuntimeError("MCP initialization failed")

    async def invoke(self, query: str) -> dict[str, Any]:
        call = {"tool": "knowledge.search", "arguments": {"query": query}}
        if self.protocol == "mcp":
            result = await self.rpc(
                "tools/call", {"name": "invoke", "arguments": call}
            )
            if result.get("isError"):
                raise RuntimeError("MCP tool failure invalidates benchmark")
            return result["structuredContent"]
        response = await self.client.post("/api/invoke", json=call)
        response.raise_for_status()
        return response.json()

    async def baseline(self) -> None:
        if self.protocol == "mcp":
            await self.rpc("ping", {})
        else:
            response = await self.client.get("/health")
            response.raise_for_status()


def agent_client(gateway: Gateway) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=gateway.url,
        trust_env=False,
        timeout=15,
        headers={
            "Authorization": f"Bearer {gateway.tokens['analyst-blue']}",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        },
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=16),
    )
