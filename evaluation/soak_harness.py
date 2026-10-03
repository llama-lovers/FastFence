"""Temporary real gateway and a trusted atomic local policy/feed bundle source."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx
import yaml

if __package__:
    from evaluation.transport_harness import Gateway, configuration
else:
    from transport_harness import Gateway, configuration


class SoakGateway(Gateway):
    pid: int
    audit_capacity: int


class BundleSource:
    def __init__(self, bundle: dict[str, Any]) -> None:
        self._lock = threading.Lock()
        self._body = json.dumps(bundle).encode()
        self.fetches = 0

    def publish(self, body: bytes) -> None:
        with self._lock:
            self._body = body

    def read(self) -> bytes:
        with self._lock:
            self.fetches += 1
            return self._body


@contextmanager
def source_server(source: BundleSource):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = source.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/bundle"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def isolated_soak(audit_capacity: int = 128):
    with TemporaryDirectory(prefix="fastfence-soak-") as temporary:
        root = Path(temporary)
        configuration(root, 0)
        bundle = {
            "policy": yaml.safe_load((root / "config/policy.yaml").read_text()),
            "feed": json.loads((root / "config/signatures.json").read_text()),
        }
        source = BundleSource(bundle)
        with source_server(source) as url, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            listener.close()
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("FASTFENCE_")
            }
            env.update(
                FASTFENCE_ROOT=str(root),
                FASTFENCE_STATE=str(root / "state"),
                FASTFENCE_CONFIG_URL=url,
                FASTFENCE_CONFIG_POLL_INTERVAL="0.1",
                FASTFENCE_AUDIT_LIMIT=str(audit_capacity),
                FASTFENCE_INSTANCE_ID="isolated-soak",
            )
            process = subprocess.Popen(
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
            gateway = SoakGateway(
                url=f"http://127.0.0.1:{port}",
                tokens=json.loads(
                    (root / "state/demo-tokens.json").read_text()
                ),
                rules=0,
                pid=process.pid,
                audit_capacity=audit_capacity,
            )
            try:
                with httpx.Client(
                    base_url=gateway.url, timeout=1, trust_env=False
                ) as client:
                    for _ in range(150):
                        if process.poll() is not None:
                            raise RuntimeError(
                                "Isolated soak gateway failed to start"
                            )
                        try:
                            if client.get("/health").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError(
                            "Isolated soak startup deadline exceeded"
                        )
                yield gateway, source, bundle
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def rss_sample(pid: int) -> int:
    value = subprocess.check_output(
        ["ps", "-o", "rss=", "-p", str(pid)], text=True, timeout=2
    ).strip()
    return int(value) * 1024
