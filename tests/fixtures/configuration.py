from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

from fastfence.modules.control.persistence.policy import PolicyStore


@pytest.fixture
def configuration(tmp_path):
    policy_path, feed_path = (
        tmp_path / "policy.yaml",
        tmp_path / "signatures.json",
    )
    policy_path.write_text(Path("config/policy.offline.yaml").read_text())
    feed_path.write_text(Path("config/signatures.json").read_text())
    return policy_path, feed_path


@pytest.fixture
def http_configuration(configuration, monkeypatch):
    policy_path, feed_path = configuration
    state = {
        "body": {
            "policy": yaml.safe_load(policy_path.read_text()),
            "feed": json.loads(feed_path.read_text()),
        },
        "status": 200,
        "exception": None,
    }

    def respond(request):
        if state["exception"]:
            raise state["exception"]
        if isinstance(state["body"], bytes):
            return httpx.Response(state["status"], content=state["body"])
        return httpx.Response(state["status"], json=state["body"])

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    store = PolicyStore(
        policy_path,
        feed_path,
        config_url="http://127.0.0.1:9444/config",
        max_source_bytes=8192,
    )
    return store, state
