from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fastfence.app import Settings, create_app
from fastfence.cli import initialize


@pytest.fixture
def project(tmp_path):
    (tmp_path / "config").mkdir()
    for name in ["policy.yaml", "signatures.json"]:
        shutil.copy(Path("config") / name, tmp_path / "config" / name)
    initialize(tmp_path / "state")
    return tmp_path


@pytest.fixture
def tokens(project):
    return json.loads((project / "state/demo-tokens.json").read_text())


@pytest.fixture
def app(project):
    return create_app(
        Settings(project, project / "state", "http://127.0.0.1:1", "http://127.0.0.1:1")
    )


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def headers(tokens, actor="analyst-blue"):
    return {"Authorization": "Bearer " + tokens[actor]}
