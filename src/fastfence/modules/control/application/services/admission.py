"""Bounded FIFO among eligible identities; one event loop, no reserved budgets."""

import asyncio
from collections import Counter, deque

from pydantic import BaseModel, ConfigDict

from fastfence.modules.control.domain.exceptions import RequestQueueError

QueueKey = tuple[str, str]


class WaitingRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    future: asyncio.Future[None]
    key: QueueKey
    limit: int
    weight: int


class RequestAdmission:
    def __init__(
        self,
        concurrency: int = 8,
        max_waiting: int = 1024,
        wait_timeout_seconds: float = 120,
        max_waiting_bytes: int = 67_108_864,
        per_identity: int = 32,
    ) -> None:
        integers = (concurrency, max_waiting, max_waiting_bytes, per_identity)
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in integers
        ):
            raise ValueError("Invalid request admission bounds")
        if not (
            1 <= concurrency <= 128
            and 0 <= max_waiting <= 4096
            and 0 < wait_timeout_seconds <= 3600
            and 1 <= max_waiting_bytes <= 268_435_456
            and 1 <= per_identity <= 1024
        ):
            raise ValueError("Invalid request admission bounds")
        self.concurrency, self.max_waiting = concurrency, max_waiting
        self.wait_timeout_seconds = wait_timeout_seconds
        self.max_waiting_bytes, self.per_identity = (
            max_waiting_bytes,
            per_identity,
        )
        self._active = 0
        self._active_keys: Counter[QueueKey] = Counter()
        self._waiting_keys: Counter[QueueKey] = Counter()
        self._waiting_bytes = 0
        self._waiting: deque[WaitingRequest] = deque()
        self._closed = False

    async def acquire(
        self, weight_bytes: int, key: QueueKey, subject_limit: int
    ) -> bool:
        if (
            isinstance(weight_bytes, bool)
            or not isinstance(weight_bytes, int)
            or weight_bytes < 0
        ):
            raise ValueError("Invalid request weight")
        if (
            isinstance(subject_limit, bool)
            or not isinstance(subject_limit, int)
            or subject_limit < 1
        ):
            raise ValueError("Invalid subject concurrency")
        if self._closed:
            raise RequestQueueError("request_queue_closed")
        self._drain()
        if (
            self._active < self.concurrency
            and self._active_keys[key] < subject_limit
        ):
            self._grant(key)
            return False
        if self._full(key, weight_bytes):
            raise RequestQueueError("request_queue_full")
        entry = WaitingRequest(
            future=asyncio.get_running_loop().create_future(),
            key=key,
            limit=subject_limit,
            weight=weight_bytes,
        )
        self._waiting.append(entry)
        self._waiting_keys[key] += 1
        self._waiting_bytes += weight_bytes
        try:
            async with asyncio.timeout(self.wait_timeout_seconds):
                await asyncio.shield(entry.future)
            return True
        except BaseException as error:
            self._withdraw(entry)
            if isinstance(error, TimeoutError):
                raise RequestQueueError("request_queue_timeout") from None
            raise

    def _full(self, key: QueueKey, weight: int) -> bool:
        return (
            len(self._waiting) >= self.max_waiting
            or self._waiting_keys[key] >= self.per_identity
            or self._waiting_bytes + weight > self.max_waiting_bytes
        )

    def _grant(self, key: QueueKey) -> None:
        self._active += 1
        self._active_keys[key] += 1

    def _remove_waiting(self, entry: WaitingRequest) -> None:
        self._waiting.remove(entry)
        self._waiting_bytes -= entry.weight
        self._waiting_keys[entry.key] -= 1
        if not self._waiting_keys[entry.key]:
            del self._waiting_keys[entry.key]

    def _withdraw(self, entry: WaitingRequest) -> None:
        future = entry.future
        try:
            self._remove_waiting(entry)
        except ValueError:
            # A grant can race with cancellation before its coroutine resumes.
            if (
                future.done()
                and not future.cancelled()
                and future.exception() is None
            ):
                self.release(entry.key)
        else:
            future.cancel()

    def _drain(self) -> None:
        for entry in tuple(self._waiting):
            if self._closed or self._active >= self.concurrency:
                break
            if self._active_keys[entry.key] >= entry.limit:
                continue
            self._remove_waiting(entry)
            if entry.future.done():
                continue
            self._grant(entry.key)
            entry.future.set_result(None)

    def release(self, key: QueueKey) -> None:
        if not self._active_keys[key]:
            raise RuntimeError("No admitted request to release")
        self._active -= 1
        self._active_keys[key] -= 1
        if not self._active_keys[key]:
            del self._active_keys[key]
        self._drain()

    def close(self) -> None:
        self._closed = True
        for entry in tuple(self._waiting):
            self._remove_waiting(entry)
            if not entry.future.done():
                entry.future.set_exception(
                    RequestQueueError("request_queue_closed")
                )

    def snapshot(self) -> dict[str, int]:
        return {
            "active": self._active,
            "waiting": len(self._waiting),
            "max_active": self.concurrency,
            "max_waiting": self.max_waiting,
            "wait_timeout_ms": int(self.wait_timeout_seconds * 1000),
            "waiting_bytes": self._waiting_bytes,
            "max_waiting_bytes": self.max_waiting_bytes,
            "per_identity": self.per_identity,
        }
