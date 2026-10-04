"""Record an actual OpenAI SDK integration against isolated public FastFence.

The launcher uses cached packages only. The protected request uses the existing
local Ollama and Laya installation; no operator configuration is changed.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path


def request(base, token, path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(
        base + path,
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        method="GET" if data is None else "PUT",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def prepare(root, laya_root):
    from fastfence.app.factory import create_app
    from fastfence.shared.settings.app_settings import AppSettings

    tokens = {name: secrets.token_urlsafe(32) for name in ["agent", "admin"]}
    records = [
        {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "identity": {
                "subject": name,
                "tenant": "integration-demo",
                "roles": ["demo"],
                "admin": name == "admin",
            },
        }
        for name, token in tokens.items()
    ]
    config = root / "config"
    config.mkdir()
    policy = {
        "version": 1,
        "description": "Isolated actual SDK demonstration",
        "tools": {},
        "models": {
            "qwen3:0.6b": {
                "roles": ["demo"],
                "max_output_tokens": 256,
                "timeout_ms": 60000,
            }
        },
        "budgets": {
            "demo": {
                "calls": 100,
                "tokens": 1000000,
                "compute_ms": 1000000,
                "cost_microusd": 0,
                "concurrent": 2,
            }
        },
        "privacy": {"enabled": True, "input": "block", "output": "redact"},
        "semantic": {
            "provider": "laya",
            "model": "qwen3:4b",
            "timeout_ms": 60000,
            "scan_output": True,
        },
        "text_rules": [],
        "signatures_enabled": True,
        "max_input_bytes": 16384,
        "max_output_bytes": 16384,
    }
    (config / "policy.yaml").write_text(json.dumps(policy))
    (config / "signatures.json").write_text(
        json.dumps({"version": 1, "signatures": []})
    )
    app = create_app(
        AppSettings(
            root=root,
            authoring_root=laya_root,
            identity_config_json=json.dumps(records),
        )
    )
    return app, tokens


def worker(args):
    import uvicorn
    from openai import APIStatusError, OpenAI

    import fastfence

    assert importlib.metadata.version("fastfence") == "1.0.7"
    assert "site-packages" in str(Path(fastfence.__file__).resolve())
    root = Path.cwd() / "operator"
    root.mkdir()
    app, tokens = prepare(root, args.laya_root)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
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
                raise RuntimeError("Isolated gateway did not start")
            time.sleep(0.05)
        run_flow(base, tokens, OpenAI, APIStatusError, args.output)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("Isolated gateway did not shut down")


def run_flow(base, tokens, client_class, error_class, output):
    status = request(base, tokens["admin"], "/api/admin/status")
    instance = status["runtime"]["instance_id"]
    started = time.perf_counter()
    with client_class(
        base_url=base + "/v1",
        api_key=tokens["agent"],
        max_retries=0,
        timeout=120,
    ) as client:
        payload = {
            "model": "qwen3:0.6b",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 256,
            "temperature": 0,
            "stream": False,
        }
        response = client.chat.completions.create(**payload)
        allowed = response.model_dump()["fastfence"]
        text = response.choices[0].message.content
        assert (
            text
            and allowed["decision"] == "allowed"
            and allowed["upstream_executed"]
        )
        allowed_ms = round((time.perf_counter() - started) * 1000, 3)
        policy = status["policy"]
        policy["version"] += 1
        policy["text_rules"] = [
            {
                "id": "demo-hello",
                "operator": "contains",
                "value": "Hello",
                "direction": "input",
                "target": "model",
                "action": "block",
            }
        ]
        published = request(base, tokens["admin"], "/api/admin/policy", policy)
        denied_start = time.perf_counter()
        try:
            client.chat.completions.create(**payload)
        except error_class as error:
            assert error.status_code == 403
            denied = error.response.json()
        else:
            raise AssertionError("Identical request unexpectedly passed")
        blocked_ms = round((time.perf_counter() - denied_start) * 1000, 3)
    final = request(base, tokens["admin"], "/api/admin/status")
    assert final["runtime"]["instance_id"] == instance
    assert final["metrics"]["semantic_calls"] == 2
    assert denied["fastfence"]["upstream_executed"] is False
    assert denied["error"]["code"] == "input_text_rule"
    audit = final["audit"]
    successful = next(
        row for row in audit if row["request_id"] == allowed["request_id"]
    )
    assert successful["semantic_input_status"] == "passed"
    assert successful["semantic_output_status"] == "passed"
    report = {
        "package_version": importlib.metadata.version("fastfence"),
        "sdk": "openai",
        "sdk_version": importlib.metadata.version("openai"),
        "installed_site_packages_verified": True,
        "public_package_cached_offline": True,
        "same_gateway_instance": True,
        "actual_business_model": "qwen3:0.6b",
        "actual_assessor": "Laya / qwen3:4b",
        "synthetic_upstream": False,
        "semantic_calls": 2,
        "allowed": {
            "http_status": 200,
            **allowed,
            "client_elapsed_ms": allowed_ms,
            "semantic_input_status": "passed",
            "semantic_output_status": "passed",
            "response_text": text,
        },
        "activated_policy_version": published["policy_version"],
        "blocked": {
            "http_status": 403,
            **denied["fastfence"],
            "reason": denied["error"]["code"],
            "client_elapsed_ms": blocked_ms,
        },
        "timing_scope": "One observed live SDK request each; not a benchmark or SLO",
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    sys.stdout.write(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--laya-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    log = root / "state/private/integration-demo-raw.log"
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("FASTFENCE_", "PYTHONPATH", "PYTHONHOME"))
    }
    with tempfile.TemporaryDirectory(prefix="fastfence-sdk-demo-") as temp:
        entry = Path(temp) / "integration_demo.py"
        shutil.copyfile(__file__, entry)
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
                    "openai==3.24.0",
                    "python",
                    str(entry),
                    "--worker",
                    "--laya-root",
                    str(args.laya_root.resolve()),
                    "--output",
                    str(args.output),
                ],
                cwd=temp,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=240,
                check=False,
            )
        if result.returncode:
            raise SystemExit(
                "Integration recording failed; inspect the private log"
            )
    sys.stdout.write(
        "Verified actual SDK integration; isolated gateway stopped.\n"
    )


if __name__ == "__main__":
    main()
