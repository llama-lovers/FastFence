"""Background configuration preparation must preserve one last-good immutable snapshot."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import yaml

from fastfence.app.factory import watch_config
from fastfence.modules.control.persistence.config_providers import (
    ConfigSourceError,
    validate_config_url,
)
from fastfence.modules.control.persistence.policy import PolicyStore


async def test_background_file_update_and_invalid_candidate_retain_last_good(
    configuration,
):
    policy_path, feed_path = configuration
    store = PolicyStore(policy_path, feed_path)
    original = store.snapshot()

    class Runtime:
        async def refresh_config(self):
            return await store.refresh()

    watcher = asyncio.create_task(watch_config(Runtime(), 0.01))
    try:
        candidate = original.policy.editable()
        candidate["version"] += 1
        candidate["tools"]["knowledge.search"]["roles"] = ["operator"]
        policy_path.write_text(yaml.safe_dump(candidate))
        deadline = time.monotonic() + 2
        while (
            store.snapshot().policy.version == 1 and time.monotonic() < deadline
        ):
            await asyncio.sleep(0.01)
        assert store.snapshot().policy.version == 2
        assert store.snapshot().policy.tools["knowledge.search"].roles == (
            "operator",
        )
        accepted = store.snapshot()
        policy_path.write_text("version: private@example.org\n")
        while (
            store.diagnostics()["refresh_failures"] == 0
            and time.monotonic() < deadline
        ):
            await asyncio.sleep(0.01)
        assert store.diagnostics()["refresh_failures"] > 0
        assert store.snapshot() is accepted
        assert "private@example.org" not in json.dumps(store.diagnostics())
    finally:
        watcher.cancel()
        with pytest.raises(asyncio.CancelledError):
            await watcher


async def test_feed_only_update_and_same_version_content_conflict(
    configuration,
):
    policy_path, feed_path = configuration
    store = PolicyStore(policy_path, feed_path)
    original = store.snapshot()
    feed = original.feed.editable()
    feed["version"] += 1
    feed["signatures"].append(
        {
            "id": "new-pattern",
            "pattern": "specific unsafe marker",
            "description": "Feed update",
        }
    )
    feed_path.write_text(json.dumps(feed))
    assert await store.refresh()
    updated = store.snapshot()
    assert updated.policy.version == original.policy.version
    assert updated.feed.version == original.feed.version + 1
    assert not await store.refresh()
    assert store.snapshot() is updated
    changed = updated.policy.editable()
    changed["privacy"]["enabled"] = False
    policy_path.write_text(yaml.safe_dump(changed))
    assert not await store.refresh()
    assert store.snapshot() is updated
    assert store.diagnostics()["last_error"] == "version_conflict"


@pytest.mark.parametrize(
    "failure",
    ["outage", "timeout", "oversize", "malformed", "rollback", "redirect"],
)
async def test_http_failure_retains_last_good_without_exposing_source_details(
    http_configuration, failure
):
    store, state = http_configuration
    original = store.snapshot()
    if failure == "outage":
        state["status"] = 503
    elif failure == "timeout":
        state["exception"] = httpx.ReadTimeout(
            "secret=password123 private@example.org"
        )
    elif failure == "oversize":
        state["body"] = b"x" * 8193
    elif failure == "malformed":
        state["body"] = b"private@example.org not-json"
    elif failure == "rollback":
        state["body"]["policy"]["version"] = 0
    else:
        state["status"] = 302
    assert not await store.refresh()
    assert store.snapshot() is original
    diagnostics = store.diagnostics()
    assert (
        diagnostics["refresh_failures"] == 1 and diagnostics["generation"] == 1
    )
    assert diagnostics["last_error"]
    assert "private@example.org" not in json.dumps(diagnostics)
    assert "password123" not in json.dumps(diagnostics)


async def test_http_bundle_updates_are_atomic_for_concurrent_snapshot_readers(
    http_configuration,
):
    store, state = http_configuration
    stopped = threading.Event()
    observed = set()
    initial = store.snapshot()
    version_offset = initial.feed.version - initial.policy.version

    def read():
        while not stopped.is_set():
            snapshot = store.snapshot()
            pair = (snapshot.policy.version, snapshot.feed.version)
            assert pair[1] - pair[0] == version_offset
            observed.add(pair)
            time.sleep(0.0002)

    with ThreadPoolExecutor(max_workers=4) as pool:
        readers = [pool.submit(read) for _ in range(4)]
        try:
            for increment in range(1, 14):
                candidate = {
                    "policy": store.snapshot().policy.editable(),
                    "feed": store.snapshot().feed.editable(),
                }
                candidate["policy"]["version"] = (
                    initial.policy.version + increment
                )
                candidate["feed"]["version"] = initial.feed.version + increment
                state["body"] = candidate
                assert await store.refresh()
        finally:
            stopped.set()
        for reader in readers:
            reader.result()
    assert (
        observed
        and store.snapshot().policy.version == initial.policy.version + 13
    )
    assert store.diagnostics()["generation"] == 14


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example.org/config",
        "https://user:secret@example.org/config",
        "file:///etc/private",
        "http://127.0.0.1/config#fragment",
    ],
)
def test_untrusted_configuration_source_forms_are_rejected(url):
    with pytest.raises(ConfigSourceError, match="invalid_source_url"):
        validate_config_url(url)


def test_source_changed_during_read_is_not_published(
    configuration, monkeypatch
):
    policy_path, feed_path = configuration
    store = PolicyStore(policy_path, feed_path)
    previous = store.snapshot()
    original_read = store.provider._read_bounded

    def mutate_between_reads(path):
        result = original_read(path)
        if path == policy_path:
            policy_path.write_text(
                policy_path.read_text() + "\n# source changed\n"
            )
        return result

    monkeypatch.setattr(store.provider, "_read_bounded", mutate_between_reads)
    with pytest.raises(ConfigSourceError, match="source_changed_during_read"):
        store.reload()
    assert store.snapshot() is previous


def test_http_management_cannot_override_authoritative_configuration(
    http_configuration, monkeypatch
):
    store, _ = http_configuration
    previous = store.snapshot()
    candidate = previous.policy.editable()
    candidate["version"] += 1
    policy = type(previous.policy).model_validate(candidate)

    def must_not_fetch(*args, **kwargs):
        pytest.fail("Read-only HTTP management attempted a provider fetch")

    monkeypatch.setattr(store.provider, "read", must_not_fetch)
    with pytest.raises(ConfigSourceError, match="read_only_source"):
        store.save(policy)
    assert store.snapshot() is previous
    assert not store.diagnostics()["management_writable"]
