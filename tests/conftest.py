from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from examples.business_tools.credentials import initialize
from examples.business_tools.tools import DemoTools
from fastfence.app.factory import create_app
from fastfence.shared.settings.app_settings import AppSettings

pytest_plugins = ["tests.fixtures.configuration"]


@pytest.fixture
def project(tmp_path):
    (tmp_path / "config").mkdir()
    shutil.copy(
        Path("examples/business_tools/policy.yaml"),
        tmp_path / "config/policy.yaml",
    )
    shutil.copy(
        Path("config/signatures.json"), tmp_path / "config/signatures.json"
    )
    initialize(tmp_path / "state")
    return tmp_path


@pytest.fixture
def tokens(project):
    return json.loads((project / "state/demo-tokens.json").read_text())


@pytest.fixture
def app(project):
    instance = create_app(
        AppSettings(
            root=project,
            state=project / "state",
            ollama_url="http://127.0.0.1:1",
            kev_url="http://127.0.0.1:1",
        ),
        tools=DemoTools(),
    )

    yield instance
    instance.state.engine.ledger.close()


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client
