from typing import Any, Literal, Protocol

from fastfence.modules.control.domain.models import (
    Assessment,
    Identity,
    Limits,
    ModelCall,
    ModelMessage,
    Policy,
    SemanticConfig,
    Snapshot,
    ToolCall,
    Verdict,
)


class IdentityPort(Protocol):
    def authenticate(self, token: str | None) -> Identity | None: ...

    def by_subject(self, subject: str) -> Identity | None: ...


class PolicyPort(Protocol):
    def snapshot(self) -> Snapshot: ...

    def save(self, policy: Policy) -> Snapshot: ...

    def reload(self) -> Snapshot: ...

    async def refresh(self) -> bool: ...

    def diagnostics(self) -> dict[str, Any]: ...


class LedgerPort(Protocol):
    def reserve(
        self,
        request_id: str,
        subject: str,
        limits: Limits,
        tokens: int,
        cost: int,
        ms: int,
    ) -> None: ...

    def settle(
        self, request_id: str, tokens: int, cost: int, compute_ms: int
    ) -> None: ...

    def append(
        self,
        subject: str,
        tenant: str,
        target: str,
        verdict: Verdict,
        *,
        event_kind: Literal["invocation", "management"] = "invocation",
    ) -> None: ...

    def audit(self, limit: int = 200) -> list[dict[str, Any]]: ...

    def budgets(self) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...

    def scope(self) -> dict[str, Any]: ...

    def record_semantic_call(self) -> None: ...

    def close(self) -> None: ...


class ToolsPort(Protocol):
    def supports(self, tool: str) -> bool: ...

    def validate(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]: ...

    async def call(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]: ...


class ScannerPort(Protocol):
    async def assess(self, text: str, config: SemanticConfig) -> Assessment: ...


class SecretsPort(Protocol):
    def redact(self, value: Any) -> tuple[Any, list[str]]: ...


class ModelsPort(Protocol):
    async def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        timeout_ms: int,
        stop: list[str] | None = None,
        messages: list[ModelMessage] | None = None,
    ) -> tuple[dict[str, Any], int]: ...


class InvocationPort(Protocol):
    async def invoke(
        self, identity: Identity, call: ToolCall | ModelCall
    ) -> Verdict: ...
