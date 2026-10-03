"""Bounded trusted configuration I/O for startup and background workers."""

from __future__ import annotations

import asyncio
import ipaddress
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
import yaml

ERROR_CODES = frozenset(
    {
        "source_too_large",
        "source_changed_during_read",
        "invalid_bundle",
        "invalid_source_url",
        "source_unavailable",
        "source_timeout",
        "version_conflict",
        "invalid_or_unavailable_bundle",
        "read_only_source",
        "unsupported_source_encoding",
    }
)


class ConfigSourceError(ValueError):
    """A sanitized code without source URLs or configuration contents."""


def sanitized_error(error: Exception) -> str:
    code = str(error) if isinstance(error, ConfigSourceError) else ""
    return code if code in ERROR_CODES else "invalid_or_unavailable_bundle"


class ConfigProvider(Protocol):
    kind: str

    def read(self) -> dict[str, Any]: ...


class FileConfigProvider:
    kind = "local_files"

    def __init__(self, policy: Path, feed: Path, max_bytes: int) -> None:
        self.policy, self.feed, self.max_bytes = policy, feed, max_bytes

    def _read_bounded(self, path: Path) -> bytes:
        with path.open("rb") as stream:
            data = stream.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise ConfigSourceError("source_too_large")
        return data

    def _fingerprints(self) -> tuple[tuple[int, int, int], ...]:
        return tuple(
            (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            for stat in (self.policy.stat(), self.feed.stat())
        )

    def read(self) -> dict[str, Any]:
        before = self._fingerprints()
        policy, feed = (
            self._read_bounded(self.policy),
            self._read_bounded(self.feed),
        )
        if before != self._fingerprints():
            raise ConfigSourceError("source_changed_during_read")
        try:
            return {"policy": yaml.safe_load(policy), "feed": json.loads(feed)}
        except (ValueError, yaml.YAMLError):
            raise ConfigSourceError("invalid_bundle") from None


def validate_config_url(url: str) -> None:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if (
            parts.username is not None
            or parts.password is not None
            or parts.fragment
            or not host
        ):
            raise ValueError
        if parts.scheme == "https":
            return
        if parts.scheme != "http":
            raise ValueError
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            raise ValueError
    except ValueError:
        raise ConfigSourceError("invalid_source_url") from None


class HttpConfigProvider:
    kind = "http_bundle"

    def __init__(self, url: str, timeout: float, max_bytes: int) -> None:
        validate_config_url(url)
        self.url, self.timeout, self.max_bytes = url, timeout, max_bytes

    def read(self) -> dict[str, Any]:
        try:
            return self._run_fetch()
        except (TimeoutError, httpx.TimeoutException):
            raise ConfigSourceError("source_timeout") from None
        except httpx.HTTPError:
            raise ConfigSourceError("source_unavailable") from None

    def _run_fetch(self) -> dict[str, Any]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._read())
        # Startup remains synchronous even when a factory is called by async code.
        # Join the worker only after its cancellable fetch closes all HTTP resources.
        with ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="fastfence-config-fetch"
        ) as worker:
            return worker.submit(asyncio.run, self._read()).result()

    async def _read(self) -> dict[str, Any]:
        async with asyncio.timeout(self.timeout):
            body = await self._fetch_body()
        try:
            data = json.loads(body)
            if not isinstance(data, dict) or set(data) != {"policy", "feed"}:
                raise ValueError
            return data
        except ValueError:
            raise ConfigSourceError("invalid_bundle") from None

    async def _fetch_body(self) -> bytearray:
        body = bytearray()
        async with httpx.AsyncClient(
            timeout=self.timeout,
            trust_env=False,
            follow_redirects=False,
            headers={"Accept-Encoding": "identity"},
        ) as client:
            async with client.stream("GET", self.url) as response:
                if response.status_code != 200:
                    raise ConfigSourceError("source_unavailable")
                if (
                    response.headers.get("Content-Encoding", "identity").lower()
                    != "identity"
                ):
                    raise ConfigSourceError("unsupported_source_encoding")
                async for chunk in response.aiter_bytes(
                    chunk_size=min(8192, self.max_bytes + 1)
                ):
                    if len(body) + len(chunk) > self.max_bytes:
                        raise ConfigSourceError("source_too_large")
                    body.extend(chunk)
        return body
