"""Verify automatic startup twice from a wheel or exact public uv tool package."""

import argparse
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

if __package__:
    from .smoke_uv_tool import request, run_checks, stop
else:
    from smoke_uv_tool import request, run_checks, stop


def private_snapshot(root):
    return {
        path: (root / path).read_bytes()
        for path in (
            "config/policy.yaml",
            "config/signatures.json",
            "state/credentials.json",
            "state/identities.json",
            "state/anonymization-keys.json",
        )
    }


def wait_ready(process, base, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Automatic startup exited before serving HTTP")
        try:
            request(base, "/health")
            return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise RuntimeError("Automatic startup exceeded its readiness deadline")


def check_ocr(root, base):
    token = json.loads((root / "state/credentials.json").read_text())[
        "local-agent"
    ]
    fixture = (
        Path(__file__).resolve().parents[1] / "examples/documents/english.png"
    )
    call = urllib.request.Request(
        base + "/api/documents/markdown?mode=extract",
        data=fixture.read_bytes(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "image/png",
        },
    )
    try:
        with urllib.request.urlopen(call, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        assert error.code == 422
        result = json.load(error)
    # This synthetic image contains an email forbidden by the default input policy.
    assert result["pages"] == 1 and result["ocr_elapsed_ms"] > 0
    assert result["verdict"]["reason"] == "input_sensitive_data"
    assert result["verdict"]["decision"] == "blocked"
    assert result["markdown"] is None
    return {"pages": 1, "decision": "blocked", "reason": "input_sensitive_data"}


def smoke(version, wheel=None):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Use an exact release version")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {"PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT", "UV_CACHE_DIR"}
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["UV_NATIVE_TLS"] = "true"
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
    ]
    if wheel:
        command.extend(["--from", str(wheel.resolve()), "fastfence"])
    else:
        command.append(f"fastfence@{version}")
    # Only the ephemeral test port is supplied: no init, serve, or setup command.
    with tempfile.TemporaryDirectory(
        prefix="fastfence-one-command-"
    ) as directory:
        root = Path(directory)
        for attempt in range(2):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            with (root / "startup.log").open("ab") as log:
                process = subprocess.Popen(
                    [*command, "--port", str(port)],
                    cwd=root,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    wait_ready(process, base, 1800)
                    assert (
                        request(base, "/openapi.json")["info"]["version"]
                        == version
                    )
                    current = private_snapshot(root)
                    if attempt == 0:
                        original = current
                        ocr_result = check_ocr(root, base)
                    else:
                        assert current == original
                        result = run_checks(root, base, version, full=True)
                finally:
                    stop(process)
    return {
        "status": "passed",
        "version": version,
        "installation": "isolated_wheel_uv_tool"
        if wheel
        else "public_pypi_uv_tool",
        "explicit_setup_or_serve_commands": False,
        "repeated_start_preserved_configuration_and_keys": True,
        "actual_ocr_first_start": ocr_result,
        **result,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = smoke(args.version, args.wheel)
    content = json.dumps(report, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    print(content)
