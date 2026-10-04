"""Cancel nonstreaming invocations without racing their request body reader."""

import asyncio
from contextlib import suppress

from starlette._utils import get_route_path
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastfence.shared.request_size import RequestBytes

INVOCATION_PATHS = frozenset(
    {
        "/api/invoke",
        "/api/models/complete",
        "/api/documents/markdown",
        "/v1/chat/completions",
        "/acp/runs",
        "/mcp",
    }
)


class InvocationConnection:
    def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.scope, self.receive, self.send = scope, receive, send
        self.body_complete = asyncio.Event()
        self.disconnected = asyncio.Event()
        self.receive_lock = asyncio.Lock()
        self.response_complete = False
        self.request_bytes = RequestBytes()
        scope["fastfence.request_bytes"] = self.request_bytes
        scope["fastfence.disconnect_event"] = self.disconnected

    async def forward_receive(self) -> Message:
        async with self.receive_lock:
            if not self.body_complete.is_set():
                message = await self.receive()
                if message["type"] == "http.request":
                    self.request_bytes.received += len(message.get("body", b""))
                if message["type"] == "http.disconnect":
                    self.disconnected.set()
                    self.body_complete.set()
                elif not message.get("more_body", False):
                    self.body_complete.set()
                return message
        # Once the body ends, the monitor exclusively owns receive().
        await self.disconnected.wait()
        return {"type": "http.disconnect"}

    async def forward_send(self, message: Message) -> None:
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            # Servers may immediately report disconnect when this is sent.
            self.response_complete = True
        await self.send(message)

    async def monitor(self, handler: asyncio.Task[None]) -> None:
        try:
            await self.body_complete.wait()
            while not self.disconnected.is_set():
                message = await self.receive()
                if message["type"] == "http.disconnect":
                    self.disconnected.set()
        finally:
            if not self.response_complete:
                handler.cancel()

    async def run(self, app: ASGIApp) -> None:
        async def invoke() -> None:
            await app(self.scope, self.forward_receive, self.forward_send)

        handler = asyncio.create_task(
            invoke(),
            name="fastfence-invocation-http",
        )
        watcher = asyncio.create_task(
            self.monitor(handler), name="fastfence-invocation-disconnect"
        )
        try:
            await handler
        except (asyncio.CancelledError, ClientDisconnect):
            if not self.disconnected.is_set():
                raise
        finally:
            if not self.response_complete:
                self.disconnected.set()
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
            if not handler.done():
                handler.cancel()
                with suppress(asyncio.CancelledError):
                    await handler


class InvocationDisconnect:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or get_route_path(scope).rstrip("/") not in INVOCATION_PATHS
        ):
            await self.app(scope, receive, send)
            return
        await InvocationConnection(scope, receive, send).run(self.app)
