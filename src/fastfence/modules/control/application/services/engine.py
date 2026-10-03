from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from fastfence.modules.control.application.services.execution import Executor
from fastfence.modules.control.application.services.inspection import (
    InputInspector,
    encode,
)
from fastfence.modules.control.contracts.ports import (
    AnonymizationPort,
    LedgerPort,
    ModelsPort,
    PolicyPort,
    ScannerPort,
    SecretsPort,
    ToolsPort,
)
from fastfence.modules.control.domain.exceptions import (
    BudgetExceededError,
    ModelUnavailableError,
    RejectedError,
    ResourceDeniedError,
)
from fastfence.modules.control.domain.models import (
    Identity,
    InvocationState,
    ModelCall,
    ToolCall,
    Verdict,
)


class Engine:
    def __init__(
        self,
        policies: PolicyPort,
        ledger: LedgerPort,
        tools: ToolsPort,
        scanner: ScannerPort,
        models: ModelsPort,
        secrets: SecretsPort | None = None,
        anonymization: AnonymizationPort | None = None,
    ) -> None:
        self.policies, self.ledger, self.tools = policies, ledger, tools
        self.scanner, self.models = scanner, models
        self.secrets = secrets
        self.anonymization = anonymization

    async def invoke(
        self,
        identity: Identity,
        call: ToolCall | ModelCall,
        *,
        inspect_only: bool = False,
        input_sink: Callable[[dict[str, Any]], None] | None = None,
        prompt_source: Callable[[], Awaitable[str]] | None = None,
        preparation_timeout_ms: int = 0,
    ) -> Verdict:
        snapshot = self.policies.snapshot()
        verdict = Verdict(
            request_id=uuid.uuid4().hex,
            decision="blocked",
            reason="access_denied",
            policy_version=snapshot.policy.version,
            feed_version=snapshot.feed.version,
            latency_ms=0,
            semantic_provider=snapshot.policy.semantic.provider,
        )
        state = InvocationState(
            identity=identity,
            call=call,
            snapshot=snapshot,
            verdict=verdict,
            started_at=time.monotonic(),
            target=call.tool
            if isinstance(call, ToolCall)
            else "llm:" + call.model,
        )
        try:
            await self._run(
                state,
                inspect_only=inspect_only,
                input_sink=input_sink,
                prompt_source=prompt_source,
                preparation_timeout_ms=preparation_timeout_ms,
            )
        except (Exception, asyncio.CancelledError) as error:
            self._mark_failure(state, error)
        finally:
            self._record(state)
        if state.cancelled:
            raise asyncio.CancelledError
        return verdict

    async def _run(
        self,
        state: InvocationState,
        *,
        inspect_only: bool,
        input_sink: Callable[[dict[str, Any]], None] | None,
        prompt_source: Callable[[], Awaitable[str]] | None,
        preparation_timeout_ms: int,
    ) -> None:
        inspector = InputInspector(self.tools, self.secrets, self.anonymization)
        executor = Executor(
            self.tools,
            self.scanner,
            self.models,
            self.ledger,
            self.secrets,
            self.anonymization,
        )
        if prompt_source is not None:
            if not 1 <= preparation_timeout_ms <= 180_000:
                raise RejectedError("invalid_document_timeout")
            prepared = inspector.admit_document(state)
        else:
            prepared = inspector.prepare(state)
        self.ledger.reserve(
            state.verdict.request_id,
            state.identity.subject,
            prepared.limits,
            prepared.reserved_tokens,
            prepared.rule.cost_microusd,
            prepared.allocated_ms + preparation_timeout_ms,
        )
        state.reserved, state.reserved_tokens = True, prepared.reserved_tokens
        if prompt_source is not None:
            state.preparing_document = True
            markdown = await asyncio.wait_for(
                prompt_source(), timeout=preparation_timeout_ms / 1000
            )
            state.call = ModelCall.model_validate(
                state.call.model_dump() | {"prompt": markdown}
            )
            state.preparing_document = False
            prepared = inspector.prepare(state)
            if prepared.reserved_tokens > state.reserved_tokens:
                raise RejectedError("document_reservation_exceeded")
        state.tokens = prepared.input_units
        if state.snapshot.policy.semantic.provider != "disabled":
            await executor.scan(
                state,
                encode(prepared.payload),
                prepared.input_units
                + state.snapshot.policy.semantic.token_allowance,
                "input",
            )
        if input_sink is not None:
            input_sink(prepared.payload)
        if inspect_only:
            assert isinstance(state.call, ModelCall)
            state.verdict.output = {
                "markdown": prepared.payload["prompt"],
                "model": state.call.model,
            }
        else:
            output = await executor.call(state, prepared)
            state.verdict.output = await executor.inspect_output(state, output)
        state.verdict.decision = "redacted" if state.findings else "allowed"
        state.verdict.reason = (
            "privacy_redacted" if state.findings else "controls_passed"
        )

    @staticmethod
    def _mark_failure(state: InvocationState, error: BaseException) -> None:
        if state.preparing_document:
            state.verdict.decision = "error"
            state.cancelled = isinstance(error, asyncio.CancelledError)
            state.verdict.reason = (
                "request_cancelled"
                if state.cancelled
                else (
                    "document_preparation_timeout"
                    if isinstance(error, TimeoutError)
                    else "document_preparation_failed"
                )
            )
            # Extraction consumed compute time, but no text/model tokens or cost.
            state.tokens = 0
            return
        if isinstance(error, RejectedError):
            state.verdict.reason = error.reason
            state.findings.update(error.findings)
            return
        if isinstance(error, BudgetExceededError):
            state.verdict.reason = str(error)
            return
        if isinstance(error, ResourceDeniedError | ValidationError):
            state.verdict.reason = (
                "cross_tenant_resource"
                if isinstance(error, ResourceDeniedError)
                else "invalid_tool_arguments"
            )
            return
        state.verdict.decision = "error"
        reasons = {
            ModelUnavailableError: "model_unavailable_fail_closed",
            TimeoutError: "upstream_timeout",
            asyncio.CancelledError: "request_cancelled",
        }
        state.verdict.reason = reasons.get(type(error), "upstream_failure")
        if state.verdict.upstream_executed or not isinstance(
            error, ModelUnavailableError
        ):
            # A failed provider reply cannot establish actual usage. Retain the
            # reservation once execution was attempted, including invalid usage.
            state.tokens = state.reserved_tokens
        state.cancelled = isinstance(error, asyncio.CancelledError)

    def _record(self, state: InvocationState) -> None:
        verdict = state.verdict
        verdict.latency_ms = max(
            1, int((time.monotonic() - state.started_at) * 1000)
        )
        verdict.findings = sorted(state.findings)
        verdict.tokens = state.tokens if state.reserved else 0
        verdict.cost_microusd = state.cost
        if state.reserved:
            self.ledger.settle(
                verdict.request_id, state.tokens, state.cost, verdict.latency_ms
            )
        self.ledger.append(
            state.identity.subject, state.identity.tenant, state.target, verdict
        )
