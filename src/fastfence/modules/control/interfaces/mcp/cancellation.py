"""Connect detached stateless MCP work to its originating HTTP connection."""

import asyncio
from collections.abc import Awaitable, Callable


async def until_disconnect[T](
    operation: Callable[[], Awaitable[T]], disconnected: asyncio.Event | None
) -> T:
    if disconnected is None:
        return await operation()
    if disconnected.is_set():
        raise asyncio.CancelledError

    async def run() -> T:
        return await operation()

    work = asyncio.create_task(run(), name="fastfence-mcp-invocation")
    watcher = asyncio.create_task(
        disconnected.wait(), name="fastfence-mcp-disconnect"
    )
    try:
        await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
        if work.done():
            return await work
        raise asyncio.CancelledError
    finally:
        if not work.done():
            work.cancel()
        watcher.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)
