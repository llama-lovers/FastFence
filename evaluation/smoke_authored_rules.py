"""Real Laya authoring and Qwen enforcement through an isolated HTTP gateway."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import yaml

from fastfence.modules.control.domain.text_rules import TextRule

if __package__:
    from evaluation.business_fixture import initialize
else:
    from business_fixture import initialize


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def author(root: Path, url: str) -> dict:
    common = [
        "integrations/laya/author-rule.sh",
        "--url",
        url,
        "--credentials",
        str(root / "state/demo-tokens.json"),
        "--sample",
        "Hello",
        "--sample",
        "Cat",
    ]
    proposal = root / "proposal.json"
    commands = [
        [
            *common,
            "--instruction",
            "Blokuj każde słowo zawierające literę a, bez rozróżniania wielkości liter.",
            "--save-proposal",
            str(proposal),
            "--output",
            str(root / "draft.json"),
        ],
        [
            *common,
            "--proposal",
            str(proposal),
            "--activate",
            "--output",
            str(root / "activation.json"),
        ],
    ]
    for index, command in enumerate(commands):
        completed = subprocess.run(command, capture_output=True, timeout=150)
        if completed.returncode:
            diagnostic = next(
                (
                    line
                    for line in completed.stderr.decode().splitlines()
                    if line.startswith("Rule authoring rejected:")
                    or line.startswith("Rule authoring failed;")
                ),
                "no sanitized diagnostic",
            )
            raise RuntimeError(f"Laya authoring stage {index}: {diagnostic}")
        if index == 0:
            rule = TextRule.model_validate_json(proposal.read_text())
            assert rule.operator == "word_contains" and rule.value == "a"
            assert rule.direction == "both" and rule.target == "model"
            assert not rule.case_sensitive
    reports = {
        name: json.loads((root / f"{name}.json").read_text())
        for name in ("draft", "activation")
    }
    assert reports["draft"]["matches"] == [False, True]
    assert reports["activation"]["matches"] == [False, True]
    return reports


def invoke(
    client: httpx.Client, headers: dict, prompt: str, max_output_tokens: int
) -> dict:
    response = client.post(
        "/api/models/complete",
        headers=headers,
        json={
            "model": "qwen3:0.6b",
            "prompt": prompt,
            "max_output_tokens": max_output_tokens,
        },
    )
    response.raise_for_status()
    return response.json()


def enforce(client: httpx.Client, tokens: dict) -> list[dict]:
    agent = {"Authorization": "Bearer " + tokens["analyst-blue"]}
    admin = {"Authorization": "Bearer " + tokens["security-admin"]}
    cases = []

    def check(
        name: str,
        prompt: str,
        reason: str,
        executed: bool,
        max_output_tokens: int = 32,
    ) -> None:
        verdict = invoke(client, agent, prompt, max_output_tokens)
        assert verdict["reason"] == reason, (name, verdict["reason"])
        assert verdict["upstream_executed"] is executed
        if reason == "controls_passed":
            assert verdict["output"]["text"].strip()
        else:
            assert (
                verdict["decision"] == "blocked" and verdict["output"] is None
            )
        cases.append(
            {
                "case": name,
                "max_output_tokens": max_output_tokens,
                **{
                    key: verdict[key]
                    for key in (
                        "request_id",
                        "decision",
                        "reason",
                        "policy_version",
                        "upstream_executed",
                        "latency_ms",
                        "findings",
                    )
                },
            }
        )

    check("input denied before Qwen", "Cat", "input_text_rule", False)
    check(
        "NFKC uppercase denied", "\uff23\uff21\uff34", "input_text_rule", False
    )
    check(
        "allowed one-token real Qwen response",
        "Hi",
        "controls_passed",
        True,
        max_output_tokens=1,
    )
    status = client.get("/api/admin/status", headers=admin).json()
    policy = status["policy"]
    policy["text_rules"][0]["direction"] = "output"
    policy["version"] += 1
    client.put(
        "/api/admin/policy", headers=admin, json=policy
    ).raise_for_status()
    check(
        "output denied after Qwen", "Say exactly Cat.", "output_text_rule", True
    )
    policy["text_rules"] = []
    policy["version"] += 1
    client.put(
        "/api/admin/policy", headers=admin, json=policy
    ).raise_for_status()
    check(
        "hot removal permits same request",
        "Say exactly Cat.",
        "controls_passed",
        True,
    )
    status = client.get("/api/admin/status", headers=admin).json()
    assert status["metrics"]["semantic_calls"] == 0
    export = client.get("/api/admin/audit.jsonl", headers=admin)
    export.raise_for_status()
    assert all(token not in export.text for token in tokens.values())
    for record in map(json.loads, export.text.splitlines()):
        assert not {"prompt", "output", "arguments"}.intersection(record)
    return cases


def run() -> dict:
    with TemporaryDirectory(prefix="fastfence-authored-") as temporary:
        root = Path(temporary)
        (root / "config").mkdir()
        shutil.copy("config/signatures.json", root / "config/signatures.json")
        policy = yaml.safe_load(
            Path("examples/business_tools/policy.yaml").read_text()
        )
        (root / "config/policy.yaml").write_text(yaml.safe_dump(policy))
        initialize(root / "state")
        tokens = json.loads((root / "state/demo-tokens.json").read_text())
        port = available_port()
        url = f"http://127.0.0.1:{port}"
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("FASTFENCE_")
        }
        env.update(
            FASTFENCE_ROOT=str(root), FASTFENCE_STATE=str(root / "state")
        )
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "evaluation.business_fixture:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with httpx.Client(
                base_url=url, trust_env=False, timeout=60
            ) as client:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Isolated gateway failed to start")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError(
                        "Isolated gateway startup deadline exceeded"
                    )
                authoring = author(root, url)
                cases = enforce(client, tokens)
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "scope": "Real Laya/Qwen3:4b drafting, exact saved-proposal activation, real Qwen3:0.6b HTTP completions; isolated temporary gateway; no semantic scanning",
            "authoring": authoring,
            "cases": cases,
            "all_passed": True,
            "audit_sanitized": True,
            "semantic_calls_during_enforcement": 0,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: {len(report['cases'])} real enforcement cases; {args.output}")
