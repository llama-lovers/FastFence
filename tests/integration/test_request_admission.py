"""The real engine queues before reservation and rechecks policy after waiting."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from fastfence.modules.control.application.services.admission import (
    RequestAdmission,
)
from fastfence.modules.control.domain.models import ModelCall
from tests.fixtures.policy import configure_policy


def setup(app, tokens, **queue):
    engine = app.state.engine
    identity = app.state.runtime.authenticate(tokens["analyst-blue"])
    engine.admission = RequestAdmission(**queue)
    engine.models.complete = AsyncMock(
        return_value=({"text": "safe reply"}, 10)
    )
    return engine, identity, (identity.tenant, identity.subject)


def call(text="hello"):
    return ModelCall(model="qwen3:0.6b", prompt=text, max_output_tokens=10)


async def waiting(engine, count=1):
    async with asyncio.timeout(1):
        while engine.admission.snapshot()["waiting"] != count:
            await asyncio.sleep(0)


async def test_subject_budget_concurrency_waits_instead_of_immediate_block(
    app, tokens
):
    engine, identity, _ = setup(app, tokens, concurrency=8)
    configure_policy(
        engine, lambda data: data["budgets"]["analyst"].update(concurrent=1)
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def complete(*_):
        entered.set()
        await release.wait()
        return {"text": "safe reply"}, 10

    engine.models.complete = AsyncMock(side_effect=complete)
    first = asyncio.create_task(engine.invoke(identity, call()))
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(engine.invoke(identity, call()))
    await waiting(engine)
    assert engine.ledger.budgets()[0]["inflight"] == 1
    assert engine.ledger.budgets()[0]["calls"] == 1
    release.set()
    results = await asyncio.wait_for(asyncio.gather(first, second), 2)
    assert all(result.decision == "allowed" for result in results)
    assert engine.ledger.budgets()[0]["inflight"] == 0
    assert engine.admission.snapshot()["active"] == 0


@pytest.mark.parametrize("kind", ["full", "timeout", "closed"])
async def test_queue_failure_has_no_reservation_or_business_call(
    app, tokens, kind
):
    engine, identity, key = setup(
        app,
        tokens,
        concurrency=1,
        max_waiting=0 if kind == "full" else 10,
        wait_timeout_seconds=0.02,
    )
    await engine.admission.acquire(1, key, 1)
    if kind == "closed":
        engine.admission.close()
    result = await engine.invoke(identity, call())
    assert (
        result.decision == "error" and result.reason == "request_queue_" + kind
    )
    assert (
        not result.upstream_executed
        and result.tokens == result.cost_microusd == 0
    )
    assert result.queue_wait_ms >= (10 if kind == "timeout" else 0)
    assert engine.ledger.budgets() == []
    engine.models.complete.assert_not_awaited()
    engine.admission.release(key)


async def test_policy_change_while_waiting_rechecks_original_content(
    app, tokens
):
    engine, identity, key = setup(app, tokens, concurrency=1)
    await engine.admission.acquire(0, key, 1)
    task = asyncio.create_task(
        engine.invoke(identity, call("restricted tomorrow"))
    )
    await waiting(engine)
    policy = configure_policy(
        engine,
        lambda data: data.update(
            text_rules=[
                {
                    "id": "new-rule",
                    "operator": "contains",
                    "value": "restricted",
                    "direction": "input",
                    "target": "model",
                }
            ]
        ),
    )
    engine.admission.release(key)
    result = await task
    assert (
        result.reason == "input_text_rule"
        and result.policy_version == policy.version
    )
    assert result.findings and not result.upstream_executed
    assert engine.ledger.budgets() == []
    engine.models.complete.assert_not_awaited()
    assert engine.admission.snapshot()["active"] == 0


async def test_precheck_findings_do_not_leak_into_changed_policy(app, tokens):
    engine, identity, key = setup(app, tokens, concurrency=1)
    configure_policy(
        engine, lambda data: data["privacy"].update(input="redact")
    )
    await engine.admission.acquire(0, key, 1)
    task = asyncio.create_task(
        engine.invoke(identity, call("synthetic@example.org"))
    )
    await waiting(engine)
    configure_policy(engine, lambda data: data["privacy"].update(enabled=False))
    engine.admission.release(key)
    result = await task
    assert result.decision == "allowed" and result.findings == []
    assert engine.models.complete.await_args.args[1] == "synthetic@example.org"


async def test_queue_wait_is_visible_but_not_compute_budget_usage(app, tokens):
    engine, identity, key = setup(app, tokens, concurrency=1)
    await engine.admission.acquire(0, key, 1)
    task = asyncio.create_task(engine.invoke(identity, call()))
    await waiting(engine)
    assert engine.ledger.budgets() == []
    await asyncio.sleep(0.05)
    engine.admission.release(key)
    result = await task
    assert result.queue_wait_ms >= 40
    assert result.latency_ms >= result.queue_wait_ms
    assert engine.ledger.budgets()[0]["compute_ms"] < result.queue_wait_ms
    assert engine.ledger.audit()[0]["queue_wait_ms"] == result.queue_wait_ms


async def test_cancelled_waiter_has_audit_and_releases_bytes(app, tokens):
    engine, identity, key = setup(app, tokens, concurrency=1)
    await engine.admission.acquire(0, key, 1)
    task = asyncio.create_task(engine.invoke(identity, call()))
    await waiting(engine)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert engine.ledger.audit()[0]["reason"] == "request_cancelled"
    assert engine.ledger.budgets() == []
    assert engine.admission.snapshot()["waiting_bytes"] == 0
    engine.models.complete.assert_not_awaited()
    engine.admission.release(key)


async def test_document_bytes_reject_before_ocr_and_reservation(app, tokens):
    engine, identity, key = setup(
        app, tokens, concurrency=1, max_waiting_bytes=1000
    )
    await engine.admission.acquire(0, key, 1)
    source = AsyncMock(return_value="document text")
    result = await engine.invoke(
        identity,
        call(),
        prompt_source=source,
        preparation_timeout_ms=1000,
        preparation_bytes=1001,
    )
    assert result.reason == "request_queue_full"
    source.assert_not_awaited()
    engine.models.complete.assert_not_awaited()
    assert engine.ledger.budgets() == []
    engine.admission.release(key)


async def test_deterministically_forbidden_request_does_not_join_full_queue(
    app, tokens
):
    engine, identity, key = setup(app, tokens, concurrency=1, max_waiting=0)
    await engine.admission.acquire(0, key, 1)
    result = await engine.invoke(identity, call("synthetic@example.org"))
    assert result.reason == "input_sensitive_data" and result.queue_wait_ms == 0
    assert engine.admission.snapshot()["waiting"] == 0
    engine.admission.release(key)


async def test_one_thousand_distinct_identity_requests_wait_and_complete(
    app, tokens
):
    engine, base_identity, _ = setup(
        app, tokens, concurrency=8, max_waiting=1024
    )
    release, occupied = asyncio.Event(), asyncio.Event()
    count = 0
    peak = 0

    async def complete(*_):
        nonlocal count, peak
        count += 1
        peak = max(peak, engine.admission.snapshot()["active"])
        if count == 8:
            occupied.set()
        await release.wait()
        await asyncio.sleep(0)
        return {"text": "controlled response"}, 10

    engine.models.complete = AsyncMock(side_effect=complete)
    tasks = [
        asyncio.create_task(
            engine.invoke(
                base_identity.model_copy(update={"subject": f"burst-{index}"}),
                call(),
            )
        )
        for index in range(1000)
    ]
    try:
        await asyncio.wait_for(occupied.wait(), 2)
        await waiting(engine, 992)
        assert len(engine.ledger.budgets()) == 8
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        assert all(result.decision == "allowed" for result in results)
        assert count == 1000 and peak == 8
        assert (
            engine.admission.snapshot()["waiting"]
            == engine.admission.snapshot()["active"]
            == 0
        )
        assert all(row["inflight"] == 0 for row in engine.ledger.budgets())
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
