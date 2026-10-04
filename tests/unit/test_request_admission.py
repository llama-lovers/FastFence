"""Bounded event-loop queue fairness and cancellation without model inference."""

import asyncio

import pytest

from fastfence.modules.control.application.services.admission import (
    RequestAdmission,
)
from fastfence.modules.control.domain.exceptions import RequestQueueError

A, B, C = ("tenant", "a"), ("tenant", "b"), ("tenant", "c")


async def waiting(queue, count):
    async with asyncio.timeout(1):
        while queue.snapshot()["waiting"] != count:
            await asyncio.sleep(0)


async def test_fifo_and_identity_fairness_without_head_of_line_blocking():
    queue = RequestAdmission(concurrency=2)
    assert await queue.acquire(10, A, 1) is False
    same = asyncio.create_task(queue.acquire(20, A, 1))
    await waiting(queue, 1)
    assert await queue.acquire(10, B, 1) is False
    later = asyncio.create_task(queue.acquire(30, C, 1))
    await waiting(queue, 2)
    queue.release(B)
    assert await later is True and not same.done()
    queue.release(A)
    assert await same is True
    assert queue.snapshot()["waiting_bytes"] == 0
    queue.release(A)
    queue.release(C)
    assert queue.snapshot()["active"] == 0


async def test_fifo_for_equally_eligible_waiters():
    queue = RequestAdmission(concurrency=1)
    await queue.acquire(0, A, 1)
    first = asyncio.create_task(queue.acquire(2, B, 1))
    await waiting(queue, 1)
    second = asyncio.create_task(queue.acquire(3, C, 1))
    await waiting(queue, 2)
    queue.release(A)
    assert await first is True and not second.done()
    queue.release(B)
    assert await second is True
    queue.release(C)


@pytest.mark.parametrize(
    "limits",
    [{"max_waiting": 1}, {"max_waiting_bytes": 10}, {"per_identity": 1}],
)
async def test_count_bytes_and_identity_bounds(limits):
    queue = RequestAdmission(concurrency=1, **limits)
    await queue.acquire(1, A, 1)
    first = asyncio.create_task(queue.acquire(10, B, 1))
    await waiting(queue, 1)
    with pytest.raises(RequestQueueError, match="request_queue_full"):
        await queue.acquire(1, B, 1)
    assert queue.snapshot()["waiting_bytes"] == 10
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert queue.snapshot()["waiting"] == queue.snapshot()["waiting_bytes"] == 0
    queue.release(A)


async def test_timeout_removes_waiter_and_keeps_active_owner():
    queue = RequestAdmission(concurrency=1, wait_timeout_seconds=0.02)
    await queue.acquire(1, A, 1)
    with pytest.raises(RequestQueueError, match="request_queue_timeout"):
        await queue.acquire(10, B, 1)
    assert queue.snapshot()["active"] == 1
    assert queue.snapshot()["waiting_bytes"] == 0
    queue.release(A)
    assert await queue.acquire(1, B, 1) is False
    queue.release(B)


async def test_cancel_after_grant_transfers_slot_to_next_waiter():
    queue = RequestAdmission(concurrency=1)
    await queue.acquire(0, A, 1)
    first = asyncio.create_task(queue.acquire(2, B, 1))
    await waiting(queue, 1)
    second = asyncio.create_task(queue.acquire(3, C, 1))
    await waiting(queue, 2)
    queue.release(A)
    first.cancel()  # Future granted, caller has not resumed yet.
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await second is True
    queue.release(C)
    assert queue.snapshot()["active"] == queue.snapshot()["waiting"] == 0


async def test_shutdown_wakes_waiters_without_releasing_active_work():
    queue = RequestAdmission(concurrency=1)
    await queue.acquire(0, A, 1)
    task = asyncio.create_task(queue.acquire(10, B, 1))
    await waiting(queue, 1)
    queue.close()
    queue.close()
    with pytest.raises(RequestQueueError, match="request_queue_closed"):
        await task
    assert queue.snapshot()["active"] == 1
    assert queue.snapshot()["waiting_bytes"] == 0
    with pytest.raises(RequestQueueError, match="request_queue_closed"):
        await queue.acquire(0, C, 1)
    queue.release(A)
    assert queue.snapshot()["active"] == 0


async def test_one_thousand_calls_drain_with_bounded_parallelism():
    queue = RequestAdmission(concurrency=8, max_waiting=1024)
    release = asyncio.Event()
    peak = 0

    async def request(index):
        nonlocal peak
        key = ("tenant", str(index))
        await queue.acquire(100, key, 1)
        try:
            peak = max(peak, queue.snapshot()["active"])
            await release.wait()
            await asyncio.sleep(0)
            return index
        finally:
            queue.release(key)

    tasks = [asyncio.create_task(request(index)) for index in range(1000)]
    await waiting(queue, 992)
    assert queue.snapshot()["waiting_bytes"] == 99200
    release.set()
    results = await asyncio.wait_for(asyncio.gather(*tasks), 3)
    assert results == list(range(1000)) and peak == 8
    assert queue.snapshot()["waiting"] == queue.snapshot()["active"] == 0
