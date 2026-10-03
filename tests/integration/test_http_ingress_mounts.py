"""ASGI mounts must preserve ingress enforcement on the routed path."""

import asyncio

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount

from fastfence.app.interfaces.http.ingress import (
    INVOCATION_BODY_BYTES,
    ProtectedRestIngress,
)
from tests.integration.test_http_ingress import raw_request


def test_mounted_application_authenticates_without_receiving_body(app):
    mounted = Starlette(routes=[Mount("/fence", app=app)])
    start, _, received = asyncio.run(
        raw_request(
            mounted, "/fence/api/invoke", [b"x" * (INVOCATION_BODY_BYTES + 1)]
        )
    )
    assert start["status"] == 401
    assert received == 0


def test_mounted_application_bounds_streamed_body(app, tokens):
    mounted = Starlette(routes=[Mount("/fence", app=app)])
    start, _, received = asyncio.run(
        raw_request(
            mounted,
            "/fence/api/invoke",
            [b"x" * (INVOCATION_BODY_BYTES + 1)],
            token=tokens["analyst-blue"],
        )
    )
    assert start["status"] == 413
    assert received == 1
    assert app.state.engine.ledger.stats()["requests"] == 0


def test_root_path_lookalike_is_not_reinterpreted_as_protected_endpoint(app):
    async def downstream(scope, receive, send):
        assert scope["path"] == "/fence-other/api/invoke"
        await JSONResponse({"routed": "unchanged"})(scope, receive, send)

    ingress = ProtectedRestIngress(
        downstream, app.state.runtime, INVOCATION_BODY_BYTES
    )

    async def configured(scope, receive, send):
        await ingress({**scope, "root_path": "/fence"}, receive, send)

    start, body, received = asyncio.run(
        raw_request(
            configured, "/fence-other/api/invoke", [b"must not be read"]
        )
    )
    assert start["status"] == 200
    assert body == b'{"routed":"unchanged"}'
    assert received == 0
