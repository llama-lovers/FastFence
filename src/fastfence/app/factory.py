import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from fastfence.app.interfaces.http.openai import create_router
from fastfence.app.interfaces.http.routes import configure_http
from fastfence.modules.control.application.facade import (
    ControlRuntime,
    build_runtime,
)
from fastfence.modules.control.interfaces.mcp.server import create_mcp
from fastfence.shared.settings.app_settings import AppSettings


async def watch_config(runtime: ControlRuntime, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        await runtime.refresh_config()


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or AppSettings.environment()
    runtime = build_runtime(settings)
    mcp = create_mcp(runtime, runtime.identities)
    mcp_app = mcp.http_app(path="/", stateless_http=True, json_response=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp_app.lifespan(app):
            watcher = asyncio.create_task(
                watch_config(runtime, settings.config_poll_interval),
                name="fastfence-config-refresh",
            )
            try:
                yield
            finally:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
                runtime.close()

    app = FastAPI(title="FastFence", version="0.1.0", lifespan=lifespan)
    app.state.engine = runtime.engine
    app.state.identities = runtime.identities
    app.state.settings = settings
    app.state.runtime = runtime
    configure_http(app, runtime)
    app.include_router(create_router(runtime))
    app.mount("/mcp", mcp_app)
    return app
