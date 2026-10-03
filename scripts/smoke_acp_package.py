"""Exercise the installed FastFence package with actual official ACP peers."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

if __package__:
    from .smoke_pypi import download_release
    from .smoke_wheel import install_package, verify_installed
else:
    from smoke_pypi import download_release
    from smoke_wheel import install_package, verify_installed

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "acp_server.py",
    "acp_gateway.py",
    "acp_client.py",
    "acp_policy.yaml",
    "signatures.json",
)
PLUGIN = """import re
from detect_secrets.plugins.base import RegexBasedDetector
class SyntheticOutputDetector(RegexBasedDetector):
    secret_type = "Synthetic output marker"  # pragma: allowlist secret
    denylist = (re.compile("SECRET OUTPUT"),)
"""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(process, url, expected):
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError(
                "Package example process exited before readiness"
            )
        try:
            with client.open(url, timeout=1) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        except OSError:
            time.sleep(0.1)
            continue
        if status == expected:
            return
        time.sleep(0.1)
    raise RuntimeError("Package example process did not become ready")


def sanitized_startup_log(path, root):
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(max(0, size - 16384))
        raw = stream.read(16384)
    if size > 16384:
        raw = raw.partition(b"\n")[2]
    content = raw.decode("utf-8", errors="replace")
    token = root / "state/examples/acp-upstream-token.txt"
    if token.is_file():
        value = token.read_text().strip()
        if value:
            content = content.replace(value, "[REDACTED]")
    credentials = root / "state/examples/acp-gateway/state/credentials.json"
    if credentials.is_file():
        for value in json.loads(credentials.read_text()).values():
            if isinstance(value, str) and value:
                content = content.replace(value, "[REDACTED]")
    return f"{path.name} (bounded diagnostic tail):\n{content[-8192:]}"


def smoke(wheel=None, *, pypi_version=None, output=None):
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {"PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT", "UV_CACHE_DIR"}
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(
        prefix="fastfence-acp-package-"
    ) as temporary:
        root = Path(temporary)
        if pypi_version:
            wheel, _ = download_release(pypi_version, root)
        assert wheel is not None
        subprocess.run(
            [
                "uv",
                "--no-config",
                "venv",
                "--python",
                "3.12",
                str(root / "venv"),
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        python = root / "venv/bin/python"
        install_package(python, wheel, root, environment, pypi_version)
        verify_installed(python, wheel, root, environment, pypi_version)
        subprocess.run(
            [
                "uv",
                "--no-config",
                "venv",
                "--python",
                "3.12",
                str(root / "sdk-venv"),
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        sdk_python = root / "sdk-venv/bin/python"
        subprocess.run(
            [
                "uv",
                "--native-tls",
                "--no-config",
                "pip",
                "install",
                "--python",
                str(sdk_python),
                "--default-index",
                "https://pypi.org/simple",
                "acp-sdk==1.0.3",
                "uvicorn==0.35.0",
                "requests==2.34.2",
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        examples = root / "examples"
        examples.mkdir()
        for name in FILES:
            shutil.copyfile(ROOT / "examples/docs" / name, examples / name)
        shutil.copyfile(
            ROOT / "scripts/acp_package_checks.py", root / "checks.py"
        )
        (root / "synthetic_detector.py").write_text(PLUGIN)
        environment["FASTFENCE_SECRET_PLUGIN_FILES"] = (
            '["' + str(root / "synthetic_detector.py") + '"]'
        )
        subprocess.run(
            [
                str(python),
                "-c",
                "from pathlib import Path; from fastfence.app.interfaces.cli.initialize import initialize_keys; initialize_keys(Path('state/examples/acp-gateway/state/anonymization-keys.json').resolve(), 'local-v1')",
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        server_port, gateway_port = free_port(), free_port()
        upstream_url = f"http://127.0.0.1:{server_port}"
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        processes = []
        logs = []
        try:
            peer_log = (root / "peer-startup.log").open("wb")
            logs.append(peer_log)
            gateway_log = (root / "gateway-startup.log").open("wb")
            logs.append(gateway_log)
            server = subprocess.Popen(
                [
                    str(sdk_python),
                    "examples/acp_server.py",
                    "--port",
                    str(server_port),
                ],
                cwd=root,
                env=environment,
                stdout=peer_log,
                stderr=peer_log,
            )
            processes.append(server)
            wait_ready(server, upstream_url + "/agents", 401)
            gateway = subprocess.Popen(
                [
                    str(python),
                    "examples/acp_gateway.py",
                    "--port",
                    str(gateway_port),
                    "--upstream-url",
                    upstream_url,
                ],
                cwd=root,
                env=environment,
                stdout=gateway_log,
                stderr=gateway_log,
            )
            processes.append(gateway)
            wait_ready(gateway, gateway_url + "/health", 200)
            subprocess.run(
                [str(sdk_python), "checks.py", gateway_url, upstream_url],
                cwd=root,
                env=environment,
                check=True,
            )
            result = json.loads((root / "acp-package-report.json").read_text())
        except Exception:
            for log in logs:
                log.flush()
                print(sanitized_startup_log(Path(log.name), root))
            raise
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for log in logs:
                log.close()
        result["package_source"] = (
            "public_pypi" if pypi_version else "built_wheel"
        )
        result["wheel"] = wheel.name
        result["sdk_and_gateway_environments_separate"] = True
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wheel", type=Path)
    source.add_argument("--pypi-version")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    smoke(
        args.wheel.resolve() if args.wheel else None,
        pypi_version=args.pypi_version,
        output=args.output,
    )
