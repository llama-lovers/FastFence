"""Bounded FIFO semantic admission preserves owner/queued cancellation isolation."""

import asyncio
import json

import pytest

from fastfence.modules.control.domain.exceptions import (
    ModelCapacityExceededError,
    ModelUnavailableError,
)
from fastfence.modules.control.domain.models import SemanticConfig, ToolCall
from fastfence.modules.control.persistence.laya_semantic import (
    MAX_PENDING_ASSESSMENTS,
    LayaSemantic,
    WorkerResult,
)
from tests.fixtures.policy import configure_policy
from tests.unit.test_laya_semantic_runtime import WorkerProcess


def config(timeout_ms=1000, **kwargs):
    return SemanticConfig(provider="laya", timeout_ms=timeout_ms, **kwargs)


def reply(severity="benign"):
    return (
        json.dumps(
            {
                "source": "real_laya",
                "content": json.dumps({"severity": severity}),
                "input_tokens": 10,
                "output_tokens": 2,
            }
        ).encode()
        + b"\n"
    )


async def payloads(process, count):
    async with asyncio.timeout(1):
        while len(process.stdin.payloads) < count:
            await asyncio.sleep(0)


async def test_two_queued_requests_keep_distinct_text_instructions_and_results(
    tmp_path,
):
    adapter = LayaSemantic(tmp_path, "http://127.0.0.1:11434")
    process = WorkerProcess()
    adapter._process = process
    first = asyncio.create_task(
        adapter.assess("first-data", config(instructions="first-policy"))
    )
    await payloads(process, 1)
    second = asyncio.create_task(
        adapter.assess("second-data", config(instructions="second-policy"))
    )
    await asyncio.sleep(0)
    assert len(process.stdin.payloads) == 1
    process.stdout.feed_data(reply())
    assert await first == (0, 12)
    await payloads(process, 2)
    process.stdout.feed_data(reply("malicious"))
    assert await second == (1, 12)
    sent = [json.loads(data) for data in process.stdin.payloads]
    assert (
        sent[0]["text"] == "first-data" and "first-policy" in sent[0]["system"]
    )
    assert "second-policy" not in sent[0]["system"]
    assert (
        sent[1]["text"] == "second-data"
        and "second-policy" in sent[1]["system"]
    )
    assert "first-policy" not in sent[1]["system"]
    assert adapter._pending == 0 and process.kills == 0
    await adapter.aclose()


async def test_waiting_timeout_does_not_kill_active_owner(tmp_path):
    adapter = LayaSemantic(tmp_path, "http://127.0.0.1:11434")
    process = WorkerProcess()
    adapter._process = process
    first = asyncio.create_task(adapter.assess("first", config()))
    await payloads(process, 1)
    with pytest.raises(TimeoutError):
        await adapter.assess("waiting", config(timeout_ms=100))
    assert adapter._pending == 1 and process.kills == 0
    process.stdout.feed_data(reply())
    assert await first == (0, 12)
    assert len(process.stdin.payloads) == 1
    await adapter.aclose()


async def test_total_pending_is_bounded_and_cancellation_frees_every_slot(
    tmp_path,
):
    adapter = LayaSemantic(tmp_path, "http://127.0.0.1:11434")
    process = WorkerProcess()
    adapter._process = process
    tasks = [
        asyncio.create_task(adapter.assess(str(i), config()))
        for i in range(MAX_PENDING_ASSESSMENTS)
    ]
    await asyncio.sleep(0)
    assert adapter._pending == MAX_PENDING_ASSESSMENTS
    with pytest.raises(ModelCapacityExceededError, match="capacity exceeded"):
        await adapter.assess("overflow", config())
    assert len(process.stdin.payloads) == 1
    for task in reversed(tasks):
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert adapter._pending == 0 and not adapter._slot.locked()
    assert process.kills == 1


async def test_close_rejects_queued_work_without_starting_it(tmp_path):
    adapter = LayaSemantic(tmp_path, "http://127.0.0.1:11434")
    process = WorkerProcess()
    adapter._process = process
    first = asyncio.create_task(adapter.assess("first", config()))
    await payloads(process, 1)
    second = asyncio.create_task(adapter.assess("second", config()))
    await asyncio.sleep(0)
    await adapter.aclose()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(results[0], ValueError)
    assert isinstance(results[1], ModelUnavailableError)
    assert len(process.stdin.payloads) == 1 and adapter._pending == 0


async def test_cancelled_owner_drops_protocol_before_queued_request_restarts(
    tmp_path, monkeypatch
):
    adapter = LayaSemantic(tmp_path, "http://127.0.0.1:11434")
    old = WorkerProcess()
    new = WorkerProcess(reply())
    adapter._process = old

    async def start():
        adapter._process = new
        return new

    monkeypatch.setattr(adapter, "_start", start)
    first = asyncio.create_task(adapter.assess("first", config()))
    await payloads(old, 1)
    second = asyncio.create_task(adapter.assess("second", config()))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await second == (0, 12)
    assert old.kills == 1 and len(new.stdin.payloads) == 1
    assert json.loads(new.stdin.payloads[0])["text"] == "second"
    await adapter.aclose()


async def test_two_engine_identities_complete_both_stages_and_settle_independently(
    app, monkeypatch
):
    engine = app.state.engine
    configure_policy(
        engine, lambda p: p["semantic"].update(provider="laya", timeout_ms=1000)
    )
    active, peak, calls = 0, 0, []

    async def exchange(text, settings):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        calls.append(text)
        await asyncio.sleep(0.01)
        active -= 1
        return WorkerResult(
            source="real_laya",
            content='{"severity":"benign"}',
            input_tokens=1,
            output_tokens=1,
        )

    monkeypatch.setattr(engine.scanner.laya, "_exchange", exchange)
    identities = [
        app.state.identities.by_subject(subject)
        for subject in ("analyst-blue", "analyst-green")
    ]
    results = await asyncio.gather(
        *[
            engine.invoke(
                identity,
                ToolCall(
                    tool="knowledge.search",
                    arguments={"query": f"forecast {i}"},
                ),
            )
            for i, identity in enumerate(identities)
        ]
    )
    assert peak == 1 and len(calls) == 4
    assert all(
        v.decision == "allowed"
        and v.semantic_input_status == v.semantic_output_status == "passed"
        for v in results
    )
    assert len({v.request_id for v in results}) == 2
    rows = engine.ledger.budgets()
    assert {r["subject"] for r in rows} == {"analyst-blue", "analyst-green"}
    assert all(r["calls"] == 1 and r["inflight"] == 0 for r in rows)
    assert engine.scanner.laya._pending == 0
    await engine.scanner.aclose()


async def test_close_during_process_creation_kills_new_child_without_sending_data(
    tmp_path, monkeypatch
):
    for name in (
        "state/laya/venv/bin/python",
        "integrations/laya/semantic_worker.py",
        "state/laya/upstream",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    adapter = LayaSemantic(tmp_path, "http://127.0.0.1:11434")
    started, release = asyncio.Event(), asyncio.Event()
    process = WorkerProcess()

    async def spawn(*args, **kwargs):
        started.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    request = asyncio.create_task(adapter.assess("never sent", config()))
    await started.wait()
    await adapter.aclose()
    release.set()
    with pytest.raises(ModelUnavailableError):
        await request
    assert process.kills == process.waits == 1
    assert process.stdin.payloads == []
    assert adapter._process is None and adapter._pending == 0
