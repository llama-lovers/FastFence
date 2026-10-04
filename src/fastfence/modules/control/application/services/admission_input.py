"""Local precheck and fresh-policy reinspection surround bounded queue waiting."""

import time
from collections.abc import Awaitable, Callable

from fastfence.modules.control.application.services.admission import (
    RequestAdmission,
)
from fastfence.modules.control.application.services.inspection import (
    InputInspector,
    encode,
)
from fastfence.modules.control.contracts.ports import PolicyPort
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import (
    InvocationState,
    PreparedInvocation,
)


class InputAdmission:
    def __init__(
        self,
        policies: PolicyPort,
        queue: RequestAdmission,
        inspector: InputInspector,
    ) -> None:
        self.policies, self.queue, self.inspector = policies, queue, inspector

    async def prepare(
        self,
        state: InvocationState,
        prompt_source: Callable[[], Awaitable[str]] | None,
        preparation_timeout_ms: int,
        preparation_bytes: int,
    ) -> PreparedInvocation:
        prepared = self._precheck(state, prompt_source, preparation_timeout_ms)
        if (
            not isinstance(preparation_bytes, int)
            or isinstance(preparation_bytes, bool)
            or preparation_bytes < 0
        ):
            raise RejectedError("invalid_preparation_size")
        weight = (
            len(state.call.model_dump_json().encode())
            + len(encode(prepared.payload).encode())
            + preparation_bytes
        )
        key = (state.identity.tenant, state.identity.subject)
        queued_at = time.monotonic()
        try:
            waited = await self.queue.acquire(
                weight, key, prepared.limits.concurrent
            )
        finally:
            state.queue_wait_seconds = time.monotonic() - queued_at
            state.verdict.queue_wait_ms = int(state.queue_wait_seconds * 1000)
        try:
            fresh = self.policies.snapshot()
            if waited or fresh != state.snapshot:
                state.snapshot = fresh
                state.verdict.policy_version, state.verdict.feed_version = (
                    fresh.policy.version,
                    fresh.feed.version,
                )
                state.verdict.semantic_provider = fresh.policy.semantic.provider
                state.findings.clear()
                state.verdict.anonymized = False
                prepared = self._precheck(
                    state, prompt_source, preparation_timeout_ms
                )
            return prepared
        except BaseException:
            self.queue.release(key)
            raise

    def _precheck(
        self,
        state: InvocationState,
        prompt_source: Callable[[], Awaitable[str]] | None,
        preparation_timeout_ms: int,
    ) -> PreparedInvocation:
        if prompt_source is not None:
            if not 1 <= preparation_timeout_ms <= 180_000:
                raise RejectedError("invalid_document_timeout")
            return self.inspector.admit_document(state)
        return self.inspector.prepare(state)
