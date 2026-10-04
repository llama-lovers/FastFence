"""Readiness is bounded, cached and non-inferential, independent of liveness."""

import asyncio
import os
import sys
from unittest.mock import AsyncMock

import httpx
import pytest

from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.modules.control.persistence import readiness


def config(provider="ollama", model="qwen3:4b"):
    return SemanticConfig(provider=provider, model=model)


def mock_inventory(monkeypatch, response):
    original = httpx.AsyncClient
    requests = []

    def transport(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path == "/api/tags"
        return response

    def client(**kwargs):
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(**kwargs, transport=httpx.MockTransport(transport))

    monkeypatch.setattr(readiness.httpx, "AsyncClient", client)
    return requests


@pytest.mark.asyncio
async def test_inventory_probe_cached_and_invalidated_by_provider_or_model(
    tmp_path, monkeypatch
):
    requests = mock_inventory(
        monkeypatch,
        httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]}),
    )
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    first = await probe.check(config())
    assert first.status == "ready" and not first.inference_tested
    assert await probe.check(config()) is first
    assert len(requests) == 1
    absent = await probe.check(config(model="other-model"))
    assert absent.status == "not_ready" and absent.reason == "model_unavailable"
    assert len(requests) == 2
    disabled = await probe.check(config(provider="disabled"))
    assert disabled.status == "ready" and disabled.reason == "not_required"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_single_flight_and_expired_cache_retry(tmp_path, monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    entered, release = asyncio.Event(), asyncio.Event()

    async def check(current):
        entered.set()
        await release.wait()
        return readiness.result(current, "prerequisites_checked")

    operation = AsyncMock(side_effect=check)
    monkeypatch.setattr(probe, "_probe", operation)
    tasks = [asyncio.create_task(probe.check(config())) for _ in range(8)]
    await entered.wait()
    release.set()
    results = await asyncio.gather(*tasks)
    assert operation.await_count == 1
    assert all(value is results[0] for value in results)
    clock[0] += 11
    await probe.check(config())
    assert operation.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b'{"models":null}',
        b'{"models":[{"name":12}]}',
        b'{"models":[],"models":[]}',
    ],
)
async def test_malformed_inventory_fails_without_echoing_provider_content(
    tmp_path, monkeypatch, body
):
    mock_inventory(monkeypatch, httpx.Response(200, content=body))
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    report = await probe.check(config())
    assert report.status == "not_ready" and report.reason == "probe_failed"
    assert body.decode() not in report.model_dump_json()


@pytest.mark.asyncio
async def test_oversized_inventory_and_redirect_fail_closed(
    tmp_path, monkeypatch
):
    mock_inventory(
        monkeypatch,
        httpx.Response(200, content=b"x" * (readiness.MAX_TAG_BYTES + 1)),
    )
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    assert (await probe.check(config())).status == "not_ready"


@pytest.mark.asyncio
async def test_missing_laya_and_unsupported_provider_do_not_probe_network(
    tmp_path, monkeypatch
):
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    model = AsyncMock()
    monkeypatch.setattr(probe, "_model_available", model)
    assert (
        await probe.check(config(provider="laya"))
    ).reason == "laya_installation_unavailable"
    assert (
        await probe.check(config(provider="kev"))
    ).reason == "provider_probe_unsupported"
    model.assert_not_called()


@pytest.mark.asyncio
async def test_successful_laya_initialize_precedes_model_inventory(
    tmp_path, monkeypatch
):
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    calls = []

    async def initialized():
        calls.append("initialize")
        return True

    async def inventory(*args):
        calls.append("inventory")
        return True

    monkeypatch.setattr(probe, "_laya_initialized", initialized)
    monkeypatch.setattr(probe, "_model_available", inventory)
    report = await probe.check(config(provider="laya"))
    assert report.reason == "prerequisites_checked"
    assert calls == ["initialize", "inventory"]
    assert report.scope == "required_semantic_prerequisites"


def fake_laya(root, body):
    interpreter = root / "state/laya/venv/bin/python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    helpers = root / "integrations/laya"
    helpers.mkdir(parents=True)
    (helpers / "semantic_worker.py").write_text(body)
    for name in ("semantic_response.py", "authoring_contracts.py"):
        (helpers / name).touch()
    client = root / "state/laya/upstream/engine/laya/llm/client.py"
    client.parent.mkdir(parents=True)
    client.touch()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_timed_out_or_cancelled_initialize_kills_and_reaps_child(
    tmp_path, monkeypatch, cancel
):
    pidfile = tmp_path / "child.pid"
    fake_laya(
        tmp_path,
        f"import asyncio,os\nfrom pathlib import Path\nasync def initialize(source,url):\n Path({str(pidfile)!r}).write_text(str(os.getpid()))\n await asyncio.sleep(60)\n",
    )
    monkeypatch.setattr(readiness, "DEADLINE_SECONDS", 0.5)
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    task = asyncio.create_task(probe.check(config(provider="laya")))
    for _ in range(100):
        if pidfile.exists():
            break
        await asyncio.sleep(0.005)
    assert pidfile.is_file()
    pid = int(pidfile.read_text())
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert (await task).reason == "probe_timeout"
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert not probe._lock.locked()


@pytest.mark.asyncio
async def test_invalid_trusted_origin_does_not_contact_network(
    tmp_path, monkeypatch
):
    probe = readiness.SemanticReadiness(
        tmp_path, "http://user:private@external.invalid"
    )
    call = AsyncMock()
    monkeypatch.setattr(probe, "_model_available", call)
    report = await probe.check(config())
    assert report.status == "not_ready"
    assert "private" not in report.model_dump_json()
    call.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requested,available,ready",
    [
        ("qwen3", "qwen3:latest", True),
        ("qwen3:4b", "qwen3:latest", False),
        ("registry:5000/team/qwen3", "registry:5000/team/qwen3:latest", True),
        ("other", "qwen3:latest", False),
    ],
)
async def test_only_implicit_latest_tag_is_normalized(
    tmp_path, monkeypatch, requested, available, ready
):
    mock_inventory(
        monkeypatch, httpx.Response(200, json={"models": [{"name": available}]})
    )
    probe = readiness.SemanticReadiness(tmp_path, "http://127.0.0.1:11434")
    report = await probe.check(config(model=requested))
    assert (report.status == "ready") is ready
