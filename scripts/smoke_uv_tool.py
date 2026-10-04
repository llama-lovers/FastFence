"""Exercise an exact public FastFence release with uv tool run outside the checkout."""

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

CLIENT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(base, path, token=None, payload=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    call = urllib.request.Request(
        base + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers=headers,
    )
    with CLIENT.open(call, timeout=120) as response:
        return json.load(response)


def activate_file(root, status, edit):
    policy = status()["policy"]
    policy["version"] += 1
    edit(policy)
    path = root / "config/policy.yaml"
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(policy, indent=2) + "\n")
    temporary.replace(path)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = status()
        if current["policy"]["version"] == policy["version"]:
            assert current["policy"] == policy
            return policy["version"]
        time.sleep(0.2)
    raise RuntimeError("The new local policy version did not become active")


def allowed(verdict):
    assert verdict["decision"] == "allowed", verdict["reason"]
    assert verdict["upstream_executed"]
    assert verdict["semantic_input_status"] == "passed"
    assert verdict["semantic_output_status"] == "passed"
    assert verdict["output"]["text"].strip()


def blocked(verdict, reason, version):
    assert verdict["decision"] == "blocked" and verdict["reason"] == reason
    assert verdict["policy_version"] == version
    assert not verdict["upstream_executed"]
    assert verdict["semantic_input_status"] == "not_run"
    assert verdict["semantic_output_status"] == "not_run"


class BudgetDayChangedError(Exception):
    """The documented UTC-day window changed during the acceptance sequence."""


def utc_day():
    return datetime.now(UTC).date().isoformat()


def check_budget_sequence(status, invoke, activate, instance, initial_day):
    day = initial_day

    def current():
        state = status()
        assert state["runtime"]["instance_id"] == instance
        if utc_day() != day:
            raise BudgetDayChangedError
        return state

    def row():
        value = next(
            (
                item
                for item in current()["budgets"]
                if item["subject"] == "local-agent"
            ),
            None,
        )
        if value is None:
            raise RuntimeError("Budget row missing within the same UTC day")
        if value["day"] != day:
            raise RuntimeError("Budget row has an unexpected UTC day")
        return value

    for attempt in range(2):
        try:
            if attempt:
                # Seed the new daily bucket after a proven rollover only.
                verdict = invoke()
                current()
                allowed(verdict)
            value = row()
            used = value["calls"]
            assert used >= 1 and value["roles"] == ["analyst"]
            active = activate(
                lambda policy, used=used: policy["budgets"]["analyst"].update(
                    calls=used
                )
            )
            current()
            verdict = invoke()
            current()
            blocked(verdict, "budget_calls", active)
            assert row()["calls"] == used
            active = activate(
                lambda policy, used=used: policy["budgets"]["analyst"].update(
                    calls=used + 1
                )
            )
            current()
            verdict = invoke()
            current()
            allowed(verdict)
            assert verdict["policy_version"] == active
            assert row()["calls"] == used + 1
            return used
        except BudgetDayChangedError:
            if attempt:
                raise RuntimeError(
                    "UTC budget day changed twice during verification"
                ) from None
            day = utc_day()
    raise RuntimeError("Budget verification did not complete")


def run_checks(root, base, version, full):
    assert request(base, "/openapi.json")["info"]["version"] == version
    credentials = json.loads((root / "state/credentials.json").read_text())

    def status():
        return request(base, "/api/admin/status", credentials["local-admin"])

    initial = status()
    instance = initial["runtime"]["instance_id"]
    model = next(iter(initial["policy"]["models"]))
    records = []

    def invoke():
        verdict = request(
            base,
            "/api/models/complete",
            credentials["local-agent"],
            {"model": model, "prompt": "Hello", "max_output_tokens": 256},
        )
        records.append(
            {
                key: verdict[key]
                for key in (
                    "request_id",
                    "decision",
                    "reason",
                    "policy_version",
                    "upstream_executed",
                    "semantic_input_status",
                    "semantic_output_status",
                )
            }
        )
        return verdict

    initial_day = utc_day()
    first = invoke()
    if not full:
        assert first["decision"] == "error"
        assert first["reason"] == "model_unavailable_fail_closed"
        assert not first["upstream_executed"]
        return {"mode": "offline_fail_closed", "checks": records}
    allowed(first)

    def add_rule(policy):
        policy.setdefault("text_rules", []).append(
            {
                "id": "manual-block-hello",
                "operator": "contains",
                "value": "hello",
                "direction": "input",
                "target": "model",
                "action": "block",
                "case_sensitive": False,
            }
        )

    active = activate_file(root, status, add_rule)
    denied = invoke()
    blocked(denied, "input_text_rule", active)
    assert "manual-block-hello" in denied["findings"]

    def remove_rule(policy):
        policy["text_rules"] = [
            rule
            for rule in policy["text_rules"]
            if rule["id"] != "manual-block-hello"
        ]

    active = activate_file(root, status, remove_rule)
    result = invoke()
    allowed(result)
    assert result["policy_version"] == active

    used = check_budget_sequence(
        status,
        invoke,
        lambda edit: activate_file(root, status, edit),
        instance,
        initial_day,
    )
    final = status()
    assert final["runtime"]["instance_id"] == instance
    by_id = {entry["request_id"]: entry for entry in final["audit"]}
    assert all(record["request_id"] in by_id for record in records)
    assert all(
        "output" not in by_id[record["request_id"]] for record in records
    )
    assert "Hello" not in json.dumps(final["audit"])
    return {
        "mode": "actual_laya_ollama_hot_reload_budget",
        "checks": records,
        "instance_preserved": True,
        "calls_before_limit": used,
        "calls_after_extension": used + 1,
        "audit_without_prompt_or_output": True,
    }


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def smoke(version, full=False):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Use an exact three-part public release version")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {"PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT", "UV_CACHE_DIR"}
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        "uv",
        "--native-tls",
        "--no-config",
        "tool",
        "run",
        "--python",
        "3.12",
        "--isolated",
        "--default-index",
        "https://pypi.org/simple",
        f"fastfence@{version}",
    ]
    with tempfile.TemporaryDirectory(prefix="fastfence-uv-tool-") as temporary:
        root = Path(temporary)
        init = [*command, "init", *([] if full else ["--config-only"])]
        for number in range(2):
            print(
                f"Initializing exact public uv tool package ({number + 1}/2)",
                flush=True,
            )
            subprocess.run(
                init, cwd=root, env=environment, check=True, timeout=1200
            )
            current = {
                path: (root / path).read_bytes()
                for path in (
                    "state/credentials.json",
                    "state/identities.json",
                    "state/anonymization-keys.json",
                    "config/policy.yaml",
                )
            }
            if number == 0:
                original = current
            else:
                assert original == current
        subprocess.run(
            [*command, "doctor"],
            cwd=root,
            env=environment,
            check=True,
            timeout=60,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(
            [*command, "serve", "--port", str(port)],
            cwd=root,
            env=environment,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    request(base, "/health")
                    break
                except (OSError, urllib.error.URLError):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "uv tool gateway exited during startup"
                        ) from None
                    time.sleep(0.2)
            else:
                raise RuntimeError("uv tool gateway startup timed out")
            result = run_checks(root, base, version, full)
        finally:
            stop(process)
    return {
        "status": "passed",
        "version": version,
        "installation": "public_pypi_uv_tool",
        "initialization_preserved_private_state": True,
        **result,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = smoke(arguments.version, arguments.full)
    content = json.dumps(report, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(content)
    print(content)
