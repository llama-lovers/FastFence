"""Verify synchronous text Agent Communication Protocol using its official SDK.

Uses isolated cached public FastFence 1.0.7, a real local uppercase peer and
actual loopback HTTP. This example explicitly disables semantic inference.
No Agent Client Protocol, A2A, sessions, streaming or LLM behavior is claimed.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from .acp_demo_services import gateway_app, peer_app, start_server
else:
    from acp_demo_services import gateway_app, peer_app, start_server


async def flow(base, tokens, calls):
    import httpx
    from acp_sdk.client import Client
    from acp_sdk.models import Message, MessagePart

    async with httpx.AsyncClient(
        base_url=base,
        headers={"Authorization": "Bearer " + tokens["admin"]},
        trust_env=False,
        timeout=15,
    ) as admin:
        first = await admin.get("/api/admin/status")
        first.raise_for_status()
        status = first.json()
        async with Client(
            base_url=base + "/acp",
            headers={"Authorization": "Bearer " + tokens["agent"]},
            trust_env=False,
            timeout=30,
        ) as client:
            agents = [agent.name async for agent in client.agents()]
            assert agents == ["uppercase"]

            async def invoke():
                return await client.run_sync(
                    agent="uppercase",
                    input=[
                        Message(
                            role="user", parts=[MessagePart(content="hello")]
                        )
                    ],
                )

            allowed = await invoke()
            assert allowed.status.value == "completed"
            assert allowed.output[0].parts[0].content == "HELLO"
            assert allowed.session_id is None and len(calls) == 1
            policy = status["policy"]
            policy["version"] += 1
            policy["text_rules"] = [
                {
                    "id": "demo-acp-hello",
                    "operator": "equals",
                    "value": "hello",
                    "case_sensitive": True,
                    "direction": "input",
                    "target": "tool",
                    "action": "block",
                }
            ]
            update = await admin.put("/api/admin/policy", json=policy)
            update.raise_for_status()
            assert update.json()["policy_version"] == 2
            blocked = await invoke()
            error = blocked.model_dump(mode="json")["error"]
            assert blocked.status.value == "failed" and not blocked.output
            assert error["data"]["reason"] == "input_text_rule"
            assert error["data"]["upstream_executed"] is False
            assert blocked.session_id is None and len(calls) == 1
        final = (await admin.get("/api/admin/status")).json()
        assert (
            final["runtime"]["instance_id"] == status["runtime"]["instance_id"]
        )
        assert final["metrics"]["semantic_calls"] == 0
        audit = final["audit"]
        before = next(
            row for row in audit if row["request_id"] == allowed.run_id.hex
        )
        after = next(
            row for row in audit if row["request_id"] == blocked.run_id.hex
        )
        assert (
            before["upstream_executed"] is True
            and before["policy_version"] == 1
        )
        assert (
            after["upstream_executed"] is False and after["policy_version"] == 2
        )
    return {
        "package_version": importlib.metadata.version("fastfence"),
        "sdk": "acp-sdk",
        "sdk_version": importlib.metadata.version("acp-sdk"),
        "protocol": "Agent Communication Protocol",
        "mode": "sync",
        "content_type": "text/plain",
        "gateway_endpoint": "/acp/runs",
        "peer_endpoint": "/runs",
        "installed_site_packages_verified": True,
        "public_package_cached_offline": True,
        "same_gateway_instance": True,
        "peer": "Official ACP SDK uppercase example agent",
        "model_inference": False,
        "semantic_provider": "disabled",
        "semantic_calls": 0,
        "discovered_agents": agents,
        "allowed": {
            "run_status": allowed.status.value,
            "output": "HELLO",
            "policy_version": 1,
            "upstream_executed": True,
            "peer_invocations": 1,
        },
        "blocked": {
            "run_status": blocked.status.value,
            "output": [],
            "reason": error["data"]["reason"],
            "policy_version": 2,
            "upstream_executed": False,
            "peer_invocations": len(calls),
        },
        "scope": "Real SDK client to FastFence to real local deterministic peer. Stateless synchronous text only; not A2A or Agent Client Protocol. No semantic or model-quality claim.",
    }


def worker(args):
    import fastfence

    assert importlib.metadata.version("fastfence") == "1.0.7"
    assert "site-packages" in str(Path(fastfence.__file__).resolve())
    calls, servers = [], []
    tokens = {name: secrets.token_urlsafe(32) for name in ("agent", "admin")}
    peer_token = secrets.token_urlsafe(32)
    try:
        peer_url = start_server(peer_app(peer_token, calls), servers)
        base = start_server(
            gateway_app(Path.cwd() / "operator", peer_url, peer_token, tokens),
            servers,
        )
        report = asyncio.run(flow(base, tokens, calls))
    finally:
        for server, thread, sock in reversed(servers):
            server.should_exit = True
            thread.join(timeout=15)
            sock.close()
            if thread.is_alive():
                raise RuntimeError("Isolated service did not shut down")
    report["owned_services_stopped"] = True
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_name("acp-demo-transcript.txt").write_text(
        "Actual Agent Communication Protocol | official acp-sdk 1.0.3 | FastFence 1.0.7\n"
        "Synchronous text only. Local uppercase peer; no LLM inference.\n\n"
        "Discover agents -> uppercase\n"
        "run_sync(agent='uppercase', input='hello') -> completed / HELLO\n"
        "policy v1 | upstream_executed=true | peer invocations=1\n"
        "Activate exact hello / input / tool rule -> policy v2\n"
        "Same run_sync call -> failed / input_text_rule / no output\n"
        "policy v2 | upstream_executed=false | peer invocations still=1\n"
        "Same running gateway. No restart. Both owned services stopped.\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    log = root / "state/private/acp-demo-raw.log"
    env = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "HOME", "LANG", "TMPDIR", "UV_CACHE_DIR"}
    }
    env["OTEL_SDK_DISABLED"] = "true"
    with tempfile.TemporaryDirectory(prefix="fastfence-acp-demo-") as temp:
        entry = Path(temp) / "record_acp_demo.py"
        shutil.copyfile(__file__, entry)
        shutil.copyfile(
            Path(__file__).with_name("acp_demo_services.py"),
            Path(temp) / "acp_demo_services.py",
        )
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
                    "--with",
                    "acp-sdk==1.0.3",
                    "--with",
                    "uvicorn==0.35.0",
                    "--with",
                    "requests==2.34.2",
                    "python",
                    str(entry),
                    "--worker",
                    "--output",
                    str(args.output),
                ],
                cwd=temp,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
        if result.returncode:
            raise SystemExit("ACP demonstration failed; inspect private log")
    sys.stdout.write("Verified actual ACP flow; isolated services stopped.\n")


if __name__ == "__main__":
    main()
