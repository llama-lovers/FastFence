"""A disconnect observer never races or buffers the protected request body."""

import asyncio

import pytest

from fastfence.app.interfaces.http.disconnect import InvocationDisconnect
from fastfence.modules.control.interfaces.mcp.cancellation import (
    until_disconnect,
)
from fastfence.shared.request_size import request_size


def scope(path="/api/invoke", method="POST"):
    return {"type": "http", "path": path, "root_path": "", "method": method}


async def test_chunks_once_disconnect_cancels_and_leaves_no_monitor():
    incoming = asyncio.Queue()
    chunks = [b"first", b"second"]
    for index, chunk in enumerate(chunks):
        incoming.put_nowait(
            {"type": "http.request", "body": chunk, "more_body": index == 0}
        )
    entered, cancelled = asyncio.Event(), asyncio.Event()
    observed = []

    async def app(_, receive, send):
        copied_scope = dict(_)
        for _ in chunks:
            observed.append((await receive())["body"])
        assert request_size(copied_scope) == sum(map(len, chunks))
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def send(_):
        pytest.fail("Disconnected request must not send a response")

    request = scope()
    task = asyncio.create_task(
        InvocationDisconnect(app)(request, incoming.get, send)
    )
    await asyncio.wait_for(entered.wait(), 1)
    incoming.put_nowait({"type": "http.disconnect"})
    await asyncio.wait_for(task, 1)
    assert cancelled.is_set() and observed == chunks
    assert request_size(request) == sum(map(len, chunks))
    assert not [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith("fastfence-invocation-")
    ]


async def test_no_prefetch_before_app_reads_and_response_race_is_safe():
    reads = 0
    completed = False
    response_sent = asyncio.Event()

    async def receive():
        nonlocal reads
        reads += 1
        if reads == 1:
            return {"type": "http.request", "body": b"body"}
        await response_sent.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            response_sent.set()
            await asyncio.sleep(0)

    async def app(_, receive, send):
        nonlocal completed
        await asyncio.sleep(0)
        assert reads == 0
        await receive()
        await send(
            {"type": "http.response.start", "status": 200, "headers": []}
        )
        await send({"type": "http.response.body", "body": b"ok"})
        await asyncio.sleep(0)
        completed = True

    await asyncio.wait_for(InvocationDisconnect(app)(scope(), receive, send), 1)
    assert completed


@pytest.mark.parametrize(
    "path,method",
    [
        ("/health", "GET"),
        ("/mcp", "GET"),
        ("/api/admin/semantic/review", "POST"),
    ],
)
async def test_other_routes_passthrough_without_reader(path, method):
    async def unused():
        pytest.fail("No request body should be read")

    async def send(_):
        pass

    async def app(request, receive, passed_send):
        assert receive is unused and passed_send is send
        assert "fastfence.request_bytes" not in request

    await InvocationDisconnect(app)(scope(path, method), unused, send)


async def test_external_cancellation_propagates_and_reaps_children():
    entered = asyncio.Event()

    async def app(_, receive, send):
        entered.set()
        await receive()

    async def receive():
        await asyncio.Event().wait()

    async def send(_):
        pass

    task = asyncio.create_task(
        InvocationDisconnect(app)(scope(), receive, send)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert not [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith("fastfence-invocation-")
    ]


async def test_mcp_disconnect_before_work_does_not_create_work():
    disconnected = asyncio.Event()
    disconnected.set()

    async def forbidden():
        pytest.fail("Disconnected operation started")

    with pytest.raises(asyncio.CancelledError):
        await until_disconnect(forbidden, disconnected)


@pytest.mark.parametrize("event", [False, True])
async def test_mcp_success_and_errors_preserved(event):
    disconnected = asyncio.Event() if event else None

    async def success():
        return "ok"

    async def failure():
        raise ValueError("fixture")

    assert await until_disconnect(success, disconnected) == "ok"
    with pytest.raises(ValueError, match="fixture"):
        await until_disconnect(failure, disconnected)
    assert not [
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith("fastfence-mcp-")
    ]
