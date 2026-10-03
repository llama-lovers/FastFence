from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import Field, StrictBool, field_serializer, model_validator

from fastfence.modules.control.domain.frozen import (
    FrozenControlModel,
    FrozenMap,
    Roles,
)
from fastfence.modules.control.domain.privacy import Privacy
from fastfence.modules.control.domain.semantic_rules import SemanticRule
from fastfence.modules.control.domain.text_rules import TextRule
from fastfence.shared.anonymization import AnonymizationConfig
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


class SemanticConfig(FrozenControlModel):
    provider: Literal["disabled", "ollama", "kev", "laya"] = "disabled"
    model: str = "qwen3:4b"
    threshold: float = Field(default=0.7, ge=0, le=1)
    timeout_ms: int = Field(default=5000, ge=100, le=60_000)
    scan_output: bool = True
    instructions: str = Field(default="", max_length=4096)
    rules: tuple[SemanticRule, ...] = Field(default=(), max_length=8)

    @property
    def policy_text(self) -> str:
        return "\n".join(
            [self.instructions]
            + [f"RULE {rule.id}: {rule.instruction}" for rule in self.rules]
        ).strip()

    def scoped(
        self,
        direction: Literal["input", "output"],
        target: Literal["model", "tool"],
    ) -> Self:
        return self.model_copy(
            update={
                "rules": tuple(
                    rule
                    for rule in self.rules
                    if rule.applies_to(direction, target)
                )
            }
        )

    @property
    def token_allowance(self) -> int:
        return 2048 + len(self.policy_text.encode())

    @model_validator(mode="after")
    def instructions_require_laya(self) -> Self:
        if (
            self.instructions.strip() or self.rules
        ) and self.provider != "laya":
            raise ValueError(
                "Natural-language semantic instructions require Laya"
            )
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Semantic rule IDs must be unique")
        if len(self.policy_text.encode()) > 8192:
            raise ValueError("Semantic policy exceeds 8192 UTF-8 bytes")
        if not self.scan_output and any(
            rule.direction != "input" for rule in self.rules
        ):
            raise ValueError("Output semantic rules require output scanning")
        return self


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
    anonymization: AnonymizationConfig = Field(
        default_factory=AnonymizationConfig
    )
    semantic: SemanticConfig = Field(default_factory=SemanticConfig)
    signatures_enabled: bool = True
    max_input_bytes: int = Field(default=16_384, ge=64, le=65_536)
    max_output_bytes: int = Field(default=16_384, ge=64, le=65_536)
    text_rules: tuple[TextRule, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def valid_roles(self) -> Policy:
        roles = set(self.budgets)
        for control in [*self.tools.values(), *self.models.values()]:
            if not set(control.roles).issubset(roles):
                raise ValueError("Every permitted role needs a budget")
        return self

    @model_validator(mode="after")
    def unique_text_rules(self) -> Policy:
        if len({rule.id for rule in self.text_rules}) != len(self.text_rules):
            raise ValueError("Text rule IDs must be unique")
        return self

    @field_serializer("text_rules")
    def serialize_text_rules(
        self, value: tuple[TextRule, ...]
    ) -> list[dict[str, Any]]:
        return [rule.model_dump(mode="json") for rule in value]

    def editable(self) -> dict[str, Any]:
        """Return independent JSON data for constructing a validated new version."""
        return self.model_dump(mode="json")


class Signature(FrozenControlModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    pattern: str = Field(min_length=4, max_length=256)
    description: str = Field(max_length=200)
    match_mode: Literal["literal", "token_sequence"] = "literal"
    max_gap: int = Field(default=128, ge=0, le=256)

    @model_validator(mode="after")
    def bounded_tokens(self) -> Self:
        if not self.pattern.strip():
            raise ValueError(
                "Signature pattern must contain non-whitespace text"
            )
        if (
            self.match_mode == "token_sequence"
            and not 2 <= len(self.pattern.split()) <= 8
        ):
            raise ValueError(
                "Token sequence signatures require two to eight tokens"
            )
        return self


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
    restore_originals: StrictBool = False


class ModelMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=65_536)


class ModelCall(StrictModel):
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(max_length=65_536)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    restore_originals: StrictBool = False
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
    semantic_input_status: Literal["not_run", "passed", "blocked", "error"] = (
        "not_run"
    )
    semantic_output_status: Literal["not_run", "passed", "blocked", "error"] = (
        "not_run"
    )
    tokens: int = 0
    cost_microusd: int = 0
    upstream_executed: bool = False
    instance_id: str | None = None
    telemetry_scope: Literal["instance"] = "instance"
    anonymized: bool = False
    restored: bool = False


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
