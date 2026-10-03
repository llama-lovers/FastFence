"""Bound protected REST input before framework JSON parsing or dependencies."""

from starlette._utils import get_route_path
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastfence.modules.control.application.facade import ControlRuntime

INVOCATION_BODY_BYTES = 512 * 1024
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BodyTooLargeError(Exception):
    pass


async def _read_bounded(receive: Receive, limit: int) -> bytes | None:
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        chunk = message.get("body", b"")
        if len(body) + len(chunk) > limit:
            raise BodyTooLargeError
        body.extend(chunk)
        if not message.get("more_body", False):
            return bytes(body)


class ProtectedRestIngress:
    def __init__(
        self,
        app: ASGIApp,
        runtime: ControlRuntime,
        management_limit: int,
    ) -> None:
        self.app = app
        self.runtime = runtime
        self.management_limit = max(INVOCATION_BODY_BYTES, management_limit)

    def _limit(self, scope: Scope) -> tuple[int, bool] | None:
        if scope["type"] != "http" or scope["method"] not in WRITE_METHODS:
            return None
        path = get_route_path(scope).rstrip("/")
        if path.startswith("/api/admin/"):
            return self.management_limit, True
        if path in {"/api/invoke", "/api/models/complete"}:
            return INVOCATION_BODY_BYTES, False
        return None

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        guard = self._limit(scope)
        if guard is None:
            await self.app(scope, receive, send)
            return
        limit, management = guard
        authorization = Headers(scope=scope).get("authorization", "")
        token = (
            authorization[7:] if authorization.startswith("Bearer ") else None
        )
        identity = self.runtime.authenticate(token)
        if identity is None:
            response = JSONResponse(
                {"detail": "Verified bearer credential required"},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        if management and not identity.admin:
            response = JSONResponse(
                {"detail": "Management credential required"}, status_code=403
            )
            await response(scope, receive, send)
            return
        try:
            body = await _read_bounded(receive, limit)
        except BodyTooLargeError:
            response = JSONResponse(
                {"detail": "Request body too large"}, status_code=413
            )
            await response(scope, receive, send)
            return
        if body is None:
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, replay, send)
