from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastfence.modules.control.application.services.inspection import (
    encode,
    inspect_payload,
)
from fastfence.modules.control.contracts.ports import (
    LedgerPort,
    ModelsPort,
    ScannerPort,
    SecretsPort,
    ToolsPort,
)
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import (
    InvocationState,
    ModelMessage,
    PreparedInvocation,
    ToolCall,
)


class Executor:
    def __init__(
        self,
        tools: ToolsPort,
        scanner: ScannerPort,
        models: ModelsPort,
        ledger: LedgerPort,
        secrets: SecretsPort | None = None,
    ) -> None:
        self.tools, self.scanner, self.models = tools, scanner, models
        self.ledger = ledger
        self.secrets = secrets

    async def scan(
        self,
        state: InvocationState,
        text: str,
        allocation: int,
        direction: Literal["input", "output"],
    ) -> None:
        config = state.snapshot.policy.semantic
        state.tokens += allocation
        self.ledger.record_semantic_call()
        assessment = await asyncio.wait_for(
            self.scanner.assess(text, config), config.timeout_ms / 1000
        )
        if assessment.tokens > allocation:
            raise RejectedError("semantic_usage_exceeded")
        state.tokens -= allocation - assessment.tokens
        state.verdict.semantic_score = max(
            state.verdict.semantic_score or 0, assessment.score
        )
        if assessment.score >= config.threshold:
            raise RejectedError(
                f"semantic_{direction}_risk", ["semantic_injection"]
            )

    async def call(
        self, state: InvocationState, prepared: PreparedInvocation
    ) -> Any:
        state.verdict.upstream_executed = True
        state.cost = prepared.rule.cost_microusd
        if isinstance(state.call, ToolCall):
            output = await asyncio.wait_for(
                self.tools.call(
                    state.call.tool, prepared.payload, state.identity
                ),
                timeout=prepared.rule.timeout_ms / 1000,
            )
            output_units = len(encode(output).encode())
        else:
            common = (
                state.call.model,
                prepared.payload.get("prompt", ""),
                prepared.max_output_tokens,
                prepared.rule.timeout_ms,
            )
            options: dict[str, Any] = {}
            if prepared.payload.get("stop") is not None:
                options["stop"] = prepared.payload["stop"]
            if "messages" in prepared.payload:
                options["messages"] = [
                    ModelMessage.model_validate(message)
                    for message in prepared.payload["messages"]
                ]
            completion = self.models.complete(*common, **options)
            output, units = await asyncio.wait_for(
                completion, timeout=prepared.rule.timeout_ms / 1000
            )
            if units > prepared.base_reserve:
                state.tokens = state.reserved_tokens
                raise RejectedError("model_usage_exceeded")
            output_units = units - prepared.input_units
        if (
            len(encode(output).encode())
            > state.snapshot.policy.max_output_bytes
        ):
            state.tokens = state.reserved_tokens
            raise RejectedError("output_too_large")
        state.tokens += max(0, output_units)
        return output

    async def inspect_output(self, state: InvocationState, output: Any) -> Any:
        output, findings = inspect_payload(
            output,
            state.snapshot,
            "output",
            self.secrets,
            target="tool" if isinstance(state.call, ToolCall) else "model",
        )
        state.findings.update(findings)
        config = state.snapshot.policy.semantic
        if config.provider != "disabled" and config.scan_output:
            await self.scan(
                state,
                encode(output),
                state.snapshot.policy.max_output_bytes + 2048,
                "output",
            )
        return output
