"""Lazy pooled model HTTP transport with bounded admission and no cookie state."""

import asyncio
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

from fastfence.modules.control.domain.exceptions import (
    ModelCapacityExceededError,
)

MAX_CONNECTIONS = 32
MAX_PENDING_REQUESTS = 128
MAX_RESPONSE_BYTES = 262_144


class RejectCookies(DefaultCookiePolicy):
    def set_ok(self, cookie: Cookie, request: Any) -> bool:
        return False

    def return_ok(self, cookie: Cookie, request: Any) -> bool:
        return False


class ModelHTTP:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._closed = False
        self._pending = 0

    def _get_client(self) -> httpx.AsyncClient:
        if self._closed:
            raise RuntimeError("Model transport closed")
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=None,
                trust_env=False,
                follow_redirects=False,
                limits=httpx.Limits(
                    max_connections=MAX_CONNECTIONS,
                    max_keepalive_connections=MAX_CONNECTIONS,
                ),
                cookies=CookieJar(policy=RejectCookies()),
            )
        return self._client

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        timeout_ms: int,
        headers: dict[str, str] | None = None,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> httpx.Response:
        if self._closed:
            raise RuntimeError("Model transport unavailable")
        if self._pending >= MAX_PENDING_REQUESTS:
            raise ModelCapacityExceededError("Model capacity exceeded")
        self._pending += 1
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                client = self._get_client()
                request_headers = {
                    "Accept": "application/json",
                    **(headers or {}),
                    "Accept-Encoding": "identity",
                }
                async with client.stream(
                    "POST",
                    url,
                    json=json,
                    headers=request_headers,
                    timeout=timeout_ms / 1000,
                ) as response:
                    response.raise_for_status()
                    if (
                        response.headers.get("content-encoding", "identity")
                        != "identity"
                    ):
                        raise ValueError("Encoded model response refused")
                    content = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if len(content) + len(chunk) > max_response_bytes:
                            raise ValueError(
                                "Model response exceeded its bound"
                            )
                        content.extend(chunk)
                    return httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        content=bytes(content),
                        request=response.request,
                    )
        finally:
            self._pending -= 1

    async def aclose(self) -> None:
        self._closed = True
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()
