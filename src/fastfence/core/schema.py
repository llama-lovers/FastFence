from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(StrictModel):
    subject: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    tenant: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    roles: list[str]
    admin: bool = False


class Limits(StrictModel):
    calls: int = Field(ge=1, le=1_000_000)
    tokens: int = Field(ge=1, le=100_000_000)
    cost_microusd: int = Field(ge=0)
    compute_ms: int = Field(ge=1)
    concurrent: int = Field(default=4, ge=1, le=100)


class ToolPolicy(StrictModel):
    roles: list[str] = Field(min_length=1)
    timeout_ms: int = Field(default=2000, ge=50, le=60_000)
    cost_microusd: int = Field(default=0, ge=0)


class Privacy(StrictModel):
    input: Literal["block", "redact"] = "block"
    output: Literal["block", "redact"] = "redact"
    enabled: bool = True


class SemanticConfig(StrictModel):
    provider: Literal["disabled", "ollama", "kev"] = "disabled"
    model: str = "qwen3:0.6b"
    threshold: float = Field(default=0.7, ge=0, le=1)
    timeout_ms: int = Field(default=5000, ge=100, le=60_000)
    scan_output: bool = True


class ModelPolicy(StrictModel):
    roles: list[str] = Field(min_length=1)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)
    cost_microusd: int = Field(default=0, ge=0)
    timeout_ms: int = Field(default=20_000, ge=50, le=60_000)


class Policy(StrictModel):
    version: int = Field(ge=1)
    description: str = Field(max_length=200)
    tools: dict[str, ToolPolicy]
    models: dict[str, ModelPolicy] = Field(default_factory=dict)
    budgets: dict[str, Limits]
    privacy: Privacy = Field(default_factory=Privacy)
    semantic: SemanticConfig = Field(default_factory=SemanticConfig)
    signatures_enabled: bool = True
    max_input_bytes: int = Field(default=16_384, ge=64, le=65_536)
    max_output_bytes: int = Field(default=16_384, ge=64, le=65_536)

    @model_validator(mode="after")
    def valid_roles(self):
        roles = set(self.budgets)
        for control in [*self.tools.values(), *self.models.values()]:
            if not set(control.roles).issubset(roles):
                raise ValueError("Every permitted role needs a budget")
        return self


class Signature(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    pattern: str = Field(min_length=4, max_length=256)
    description: str = Field(max_length=200)


class SignatureFeed(StrictModel):
    version: int = Field(ge=1)
    signatures: list[Signature] = Field(max_length=200)


class ToolCall(StrictModel):
    tool: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,64}$")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModelCall(StrictModel):
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(max_length=65_536)
    max_output_tokens: int = Field(default=256, ge=1, le=2048)


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
