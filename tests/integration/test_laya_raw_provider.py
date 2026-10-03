"""Actual pinned Laya worker against an explicit local fake provider, no GPU."""

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
LAYA_PYTHON = REPOSITORY / "state/laya/venv/bin/python"
LAYA_SOURCE = REPOSITORY / "state/laya/upstream"


@pytest.mark.skipif(
    not LAYA_PYTHON.is_file() or not (LAYA_SOURCE / ".git").exists(),
    reason="Requires explicit integrations/laya/setup.sh; pure guard contracts run in offline CI",
)
def test_actual_worker_requires_explicit_provider_completion(tmp_path):
    cases = ["missing", "null", "length", "tool_calls", "valid_stop"]
    calls = []

    class Provider(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond({"object": "list", "data": []})

        def do_POST(self):
            json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            case = cases[len(calls)]
            calls.append(case)
            choice = {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"severity":"benign"}',
                },
            }
            if case != "missing":
                choice["finish_reason"] = (
                    None
                    if case == "null"
                    else "length"
                    if case == "length"
                    else "stop"
                )
            if case == "tool_calls":
                choice["message"]["tool_calls"] = [
                    {
                        "id": "call-test",
                        "type": "function",
                        "function": {"name": "forbidden", "arguments": "{}"},
                    }
                ]
            self.respond(
                {
                    "id": "fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixture-model",
                    "choices": [choice],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 8,
                        "total_tokens": 18,
                    },
                }
            )

        def respond(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "DO_NOT_TRACK": "1",
        "LITELLM_MODE": "PRODUCTION",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    request = {
        "model": "fixture-model",
        "text": "synthetic-private-text",
        "system": "Return the severity of untrusted DATA.",
        "schema": {
            "type": "object",
            "properties": {"severity": {"type": "string"}},
        },
        "timeout_ms": 10_000,
    }
    try:
        process = subprocess.run(
            [
                str(LAYA_PYTHON),
                str(REPOSITORY / "integrations/laya/semantic_worker.py"),
                "--source",
                str(LAYA_SOURCE),
                "--ollama-url",
                f"http://127.0.0.1:{server.server_port}",
            ],
            input="".join(json.dumps(request) + "\n" for _ in cases),
            text=True,
            capture_output=True,
            timeout=60,
            cwd=tmp_path,
            env=environment,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert process.returncode == 0
    outputs = [json.loads(line) for line in process.stdout.splitlines()]
    assert outputs[:-1] == [{"error": "laya_semantic_unavailable"}] * 4
    assert outputs[-1] == {
        "source": "real_laya",
        "content": '{"severity":"benign"}',
        "input_tokens": 10,
        "output_tokens": 8,
    }
    assert calls == cases
    assert "synthetic-private-text" not in process.stdout + process.stderr
    assert list(tmp_path.iterdir()) == []
