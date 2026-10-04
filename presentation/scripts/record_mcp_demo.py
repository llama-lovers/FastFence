"""Record real FastMCP HTTP calls through an isolated public FastFence package.

Copies the tracked working example into an external directory. The operation
really uppercases text through the example's private FastMCP backend; there are
no simulated results, model calls, or operator configuration changes.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


def summary(verdict):
    return {
        key: verdict[key]
        for key in (
            "request_id",
            "policy_version",
            "feed_version",
            "decision",
            "reason",
            "upstream_executed",
            "tokens",
            "output",
            "semantic_input_status",
            "semantic_output_status",
        )
    }


async def exercise(base, credentials, counter, output):
    import httpx
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    admin = {"Authorization": "Bearer " + credentials["local-admin"]}
    async with httpx.AsyncClient(
        base_url=base, trust_env=False, timeout=15
    ) as http:
        unauthorized = await http.post("/mcp/", json={})
        assert unauthorized.status_code == 401
        state = (await http.get("/api/admin/status", headers=admin)).json()
        instance = state["runtime"]["instance_id"]
        async with Client(
            base + "/mcp/", auth=BearerAuth(credentials["local-agent"])
        ) as client:
            listed = await client.list_tools()
            names = sorted(tool.name for tool in listed)
            assert {"invoke", "complete"} <= set(names)
            arguments = {
                "tool": "text.uppercase",
                "arguments": {"text": "hello"},
            }
            started = time.perf_counter()
            allowed = (await client.call_tool("invoke", arguments)).data
            allowed_ms = round((time.perf_counter() - started) * 1000, 3)
            assert allowed["decision"] == "allowed"
            assert allowed["output"] == {"text": "HELLO"}
            assert allowed["upstream_executed"] is True and counter.calls == 1
            calls_before = counter.calls
            policy = state["policy"]
            policy["version"] += 1
            policy["text_rules"].append(
                {
                    "id": "demo-mcp-hello",
                    "operator": "contains",
                    "value": "hello",
                    "direction": "input",
                    "target": "tool",
                    "action": "block",
                }
            )
            published = await http.put(
                "/api/admin/policy", headers=admin, json=policy
            )
            published.raise_for_status()
            started = time.perf_counter()
            blocked = (await client.call_tool("invoke", arguments)).data
            blocked_ms = round((time.perf_counter() - started) * 1000, 3)
            assert blocked["decision"] == "blocked"
            assert blocked["reason"] == "input_text_rule"
            assert (
                blocked["upstream_executed"] is False
                and blocked["output"] is None
            )
            assert counter.calls == calls_before == 1
        final = (await http.get("/api/admin/status", headers=admin)).json()
        assert final["runtime"]["instance_id"] == instance
        assert final["metrics"]["semantic_calls"] == 0
    report = {
        "package_version": importlib.metadata.version("fastfence"),
        "sdk": "FastMCP",
        "sdk_version": importlib.metadata.version("fastmcp"),
        "installed_site_packages_verified": True,
        "source": "public_pypi_cached_offline",
        "transport": "Actual MCP Streamable HTTP",
        "endpoint": "/mcp/",
        "operation": "text.uppercase via private FastMCP backend",
        "operation_source": "examples/docs/fastmcp_server.py",
        "mocked_protocol_results": False,
        "model_calls": 0,
        "unauthenticated_http_status": unauthorized.status_code,
        "discovered_tools": names,
        "same_gateway_instance": True,
        "same_client_context": True,
        "allowed": {**summary(allowed), "client_elapsed_ms": allowed_ms},
        "blocked": {**summary(blocked), "client_elapsed_ms": blocked_ms},
        "backend_calls_after_allow": calls_before,
        "backend_calls_after_block": counter.calls,
        "scope": "Actual deterministic tool integration; observed timings are not a benchmark",
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    transcript = (
        f"Recorded MCP integration | FastFence {report['package_version']}\n"
        "Actual FastMCP HTTP client -> FastFence /mcp/ -> private FastMCP tool\n"
        f"Unauthenticated request -> HTTP {unauthorized.status_code}\n"
        f"tools/list -> {', '.join(names)}\n"
        f'invoke text.uppercase {{"text":"hello"}} -> ALLOWED / {{"text":"HELLO"}} / policy v{allowed["policy_version"]}\n'
        "Backend executions: 1\n"
        f"Activate input/tool contains hello -> policy v{blocked['policy_version']}\n"
        "Same MCP invocation -> BLOCKED / input_text_rule / upstream_executed=false\n"
        "Backend executions: still 1. Same gateway; no restart.\n"
        "Real deterministic tool. No model inference in this protocol demonstration.\n"
    )
    output.with_name("mcp-demo-transcript.txt").write_text(transcript)
    sys.stdout.write(transcript)


def worker(args):
    import fastmcp_server as example
    import uvicorn

    import fastfence

    assert importlib.metadata.version("fastfence") == "1.0.7"
    assert "site-packages" in str(Path(fastfence.__file__).resolve())

    class CountedTools(example.ProtectedMCPTools):
        calls = 0

        async def call(self, tool, arguments, identity):
            type(self).calls += 1
            return await super().call(tool, arguments, identity)

    example.ProtectedMCPTools = CountedTools
    root = Path.cwd() / "operator"
    app = example.build_example(root)
    credentials = json.loads((root / "state/credentials.json").read_text())
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="error", access_log=False)
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Isolated MCP gateway did not start")
            time.sleep(0.05)
        asyncio.run(exercise(base, credentials, CountedTools, args.output))
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("Isolated MCP gateway did not stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("FASTFENCE_", "PYTHONPATH", "PYTHONHOME"))
    }
    with tempfile.TemporaryDirectory(prefix="fastfence-mcp-demo-") as temp:
        entry = Path(temp) / "record_mcp_demo.py"
        shutil.copyfile(__file__, entry)
        for name in ["fastmcp_server.py", "policy.yaml", "signatures.json"]:
            shutil.copyfile(repo / "examples/docs" / name, Path(temp) / name)
        log = repo / "state/private/mcp-demo-raw.log"
        with log.open("w") as stream:
            result = subprocess.run(
                [
                    "uv",
                    "--offline",
                    "--no-config",
                    "run",
                    "--no-project",
                    "--python",
                    "3.12",
                    "--with",
                    "fastfence==1.0.7",
                    "python",
                    str(entry),
                    "--worker",
                    "--output",
                    str(output),
                ],
                cwd=temp,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=90,
                check=False,
            )
        if result.returncode:
            raise SystemExit("MCP demonstration failed; inspect private log")
    sys.stdout.write(
        "Real MCP allow/block verified; isolated gateway stopped.\n"
    )


if __name__ == "__main__":
    main()
