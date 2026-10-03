from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, field_serializer, model_validator

from fastfence.modules.control.domain.frozen import (
    FrozenControlModel,
    FrozenMap,
    Roles,
)
from fastfence.shared.models import StrictModel


class Identity(FrozenControlModel):
    subject: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    tenant: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    roles: Roles
    admin: bool = False


class Limits(FrozenControlModel):
    calls: int = Field(ge=1, le=1_000_000)
    tokens: int = Field(ge=1, le=100_000_000)
    cost_microusd: int = Field(ge=0)
    compute_ms: int = Field(ge=1)
    concurrent: int = Field(default=4, ge=1, le=100)


class ToolPolicy(FrozenControlModel):
    roles: Roles = Field(min_length=1)
    timeout_ms: int = Field(default=2000, ge=50, le=60_000)
    cost_microusd: int = Field(default=0, ge=0)


class Privacy(FrozenControlModel):
    input: Literal["block", "redact"] = "block"
    output: Literal["block", "redact"] = "redact"
    enabled: bool = True


class SemanticConfig(FrozenControlModel):
    provider: Literal["disabled", "ollama", "kev"] = "disabled"
    model: str = "qwen3:0.6b"
    threshold: float = Field(default=0.7, ge=0, le=1)
    timeout_ms: int = Field(default=5000, ge=100, le=60_000)
    scan_output: bool = True


class ModelPolicy(FrozenControlModel):
    roles: Roles = Field(min_length=1)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    cost_microusd: int = Field(default=0, ge=0)
    timeout_ms: int = Field(default=20_000, ge=50, le=60_000)


class Policy(FrozenControlModel):
    version: int = Field(ge=1)
    description: str = Field(max_length=200)
    tools: FrozenMap[ToolPolicy]
    models: FrozenMap[ModelPolicy] = Field(default_factory=dict)
    budgets: FrozenMap[Limits]
    privacy: Privacy = Field(default_factory=Privacy)
    semantic: SemanticConfig = Field(default_factory=SemanticConfig)
    signatures_enabled: bool = True
    max_input_bytes: int = Field(default=16_384, ge=64, le=65_536)
    max_output_bytes: int = Field(default=16_384, ge=64, le=65_536)

    @model_validator(mode="after")
    def valid_roles(self) -> Policy:
        roles = set(self.budgets)
        for control in [*self.tools.values(), *self.models.values()]:
            if not set(control.roles).issubset(roles):
                raise ValueError("Every permitted role needs a budget")
        return self

    def editable(self) -> dict[str, Any]:
        """Return independent JSON data for constructing a validated new version."""
        return self.model_dump(mode="json")


class Signature(FrozenControlModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    pattern: str = Field(min_length=4, max_length=256)
    description: str = Field(max_length=200)


class SignatureFeed(FrozenControlModel):
    version: int = Field(ge=1)
    signatures: tuple[Signature, ...] = Field(max_length=200)

    @field_serializer("signatures")
    def serialize_signatures(
        self, value: tuple[Signature, ...]
    ) -> list[dict[str, Any]]:
        return [signature.model_dump(mode="json") for signature in value]

    def editable(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ToolCall(StrictModel):
    tool: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,64}$")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModelMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=65_536)


class ModelCall(StrictModel):
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(max_length=65_536)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    stop: list[Annotated[str, Field(min_length=1, max_length=128)]] | None = (
        Field(default=None, min_length=1, max_length=4)
    )
    messages: list[ModelMessage] | None = Field(
        default=None, min_length=1, max_length=32
    )

    @model_validator(mode="after")
    def exclusive_input(self) -> ModelCall:
        if self.messages is not None and self.prompt:
            raise ValueError("Use either prompt or native messages, not both")
        return self


class Verdict(StrictModel):
    request_id: str
    decision: Literal["allowed", "redacted", "blocked", "error"]
    reason: str
    policy_version: int
    feed_version: int
    latency_ms: int
    findings: list[str] = Field(default_factory=list)
    output: Any = None
    semantic_provider: str
    semantic_score: float | None = None
    tokens: int = 0
    cost_microusd: int = 0
    upstream_executed: bool = False
    instance_id: str | None = None
    telemetry_scope: Literal["instance"] = "instance"


class Snapshot(FrozenControlModel):
    policy: Policy
    feed: SignatureFeed


class Assessment(StrictModel):
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    tokens: int = Field(ge=0)


class InvocationState(StrictModel):
    identity: Identity
    call: ToolCall | ModelCall
    snapshot: Snapshot
    verdict: Verdict
    started_at: float
    target: str
    reserved: bool = False
    reserved_tokens: int = 0
    tokens: int = 0
    cost: int = 0
    cancelled: bool = False
    findings: set[str] = Field(default_factory=set)


class PreparedInvocation(StrictModel):
    rule: ToolPolicy | ModelPolicy
    limits: Limits
    payload: dict[str, Any]
    input_units: int
    max_output_tokens: int
    base_reserve: int
    reserved_tokens: int
    allocated_ms: int
