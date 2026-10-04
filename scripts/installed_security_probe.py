"""Only provenance, network isolation and sanitized result recording."""

import hashlib
import importlib.metadata
import json
import os
import platform
import socket
import sys
from pathlib import Path

records = {}
network_attempts = 0


def provenance():
    import fastfence

    package = Path(fastfence.__file__).resolve().parent
    prefix = Path(sys.prefix).resolve()
    assert package.is_relative_to(prefix) and "site-packages" in package.parts
    assert (
        importlib.metadata.version("fastfence") == os.environ["VERIFY_VERSION"]
    )
    forbidden = Path(os.environ["VERIFY_SOURCE"]).resolve()
    assert not any(
        Path(p or ".").resolve().is_relative_to(forbidden) for p in sys.path
    )
    for name, module in list(sys.modules.items()):
        if name == "fastfence" or name.startswith("fastfence."):
            path = getattr(module, "__file__", None)
            if path:
                assert Path(path).resolve().is_relative_to(package)
    return {
        "version": importlib.metadata.version("fastfence"),
        "installed_distribution": True,
        "checkout_imports_excluded": True,
    }


def deny_network(*args, **kwargs):
    global network_attempts
    network_attempts += 1
    raise OSError("Real network is disabled in offline security verification")


def pytest_sessionstart(session):
    provenance()
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network


def pytest_runtest_logreport(report):
    key = hashlib.sha256(report.nodeid.encode()).hexdigest()
    old = records.get(key)
    if report.when == "call" or report.failed or report.skipped:
        if old is None or old["outcome"] == "passed":
            records[key] = {
                "id": key,
                "test": report.nodeid.split("[")[0],
                "outcome": report.outcome,
            }


def pytest_sessionfinish(session, exitstatus):
    result = {
        "package": provenance(),
        "exit_code": int(exitstatus),
        "collected": session.testscollected,
        "results": list(records.values()),
        "blocked_network_attempts": network_attempts,
        "python": platform.python_version(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "fastfence",
                "pytest",
                "pytest-asyncio",
                "pydantic",
                "detect-secrets",
            )
        },
    }
    Path("security-results.json").write_text(json.dumps(result))
