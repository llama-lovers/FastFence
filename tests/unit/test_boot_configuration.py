"""A runtime can boot from trusted read-only configuration without durable state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from fastfence.app.factory import create_app
from fastfence.modules.control.domain.models import ToolCall
from fastfence.modules.control.persistence.config_providers import (
    FileConfigProvider,
)
from fastfence.shared.settings.app_settings import AppSettings

TOKEN = "synthetic-startup-credential"
RECORDS = [
    {
        "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        "identity": {
            "subject": "standalone",
            "tenant": "blue",
            "roles": ["analyst"],
        },
    }
]


def prevent_state_writes(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime startup attempted durable state creation")

    for owner, name in [
        (Path, "mkdir"),
        (Path, "write_text"),
        (Path, "write_bytes"),
        (sqlite3, "connect"),
    ]:
        monkeypatch.setattr(owner, name, forbidden)
    return forbidden


async def test_inline_identities_boot_without_writable_state(
    tmp_path, configuration, monkeypatch
):
    policy_path, feed_path = configuration
    root = tmp_path / "runtime"
    (root / "config").mkdir(parents=True)
    (root / "config/policy.yaml").write_text(policy_path.read_text())
    (root / "config/signatures.json").write_text(feed_path.read_text())
    missing_state = root / "nonexistent-state"
    settings = AppSettings(
        root=root,
        state=missing_state,
        identity_config_json=json.dumps(RECORDS),
        instance_id="inline",
    )
    prevent_state_writes(monkeypatch)
    app = create_app(settings)
    try:
        identity = app.state.identities.authenticate(TOKEN)
        assert identity is app.state.identities.authenticate(TOKEN)
        result = await app.state.engine.invoke(
            identity,
            ToolCall(tool="knowledge.search", arguments={"query": "forecast"}),
        )
        assert result.decision == "allowed" and result.instance_id == "inline"
        assert not missing_state.exists()
        assert app.state.engine.ledger.stats()["storage"] == "memory"
    finally:
        app.state.runtime.close()


async def test_http_bundle_and_inline_identities_need_no_local_configuration_files(
    tmp_path, http_configuration, monkeypatch
):
    settings = AppSettings(
        root=tmp_path / "absent-root",
        identity_config_json=json.dumps(RECORDS),
        config_url="http://127.0.0.1:9444/config",
        instance_id="http-inline",
    )
    forbidden = prevent_state_writes(monkeypatch)
    monkeypatch.setattr(FileConfigProvider, "read", forbidden)
    app = create_app(settings)
    try:
        assert app.state.runtime.diagnostics()["source_kind"] == "http_bundle"
        result = await app.state.engine.invoke(
            app.state.identities.authenticate(TOKEN),
            ToolCall(tool="knowledge.search", arguments={"query": "forecast"}),
        )
        assert result.decision == "allowed"
        assert not settings.root.exists()
    finally:
        app.state.runtime.close()
