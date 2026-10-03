"""Reviewable data-only examples; these are not executable or full runtime ALLOWs."""

from typing import Literal

from pydantic import Field, field_validator

from fastfence.modules.control.domain.frozen import FrozenControlModel

type LocalDecision = Literal["blocked", "redacted", "no_local_match"]


class PolicySample(FrozenControlModel):
    target: Literal["model", "tool"] = "model"
    direction: Literal["input", "output"] = "input"
    text: str = Field(max_length=4096)

    @field_validator("text")
    @classmethod
    def bounded_text(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 4096:
            raise ValueError("Sample text exceeds byte limit")
        return value


class GeneratedPolicyTest(PolicySample):
    label: str = Field(min_length=1, max_length=100)
    expected_decision: LocalDecision

    @field_validator("label")
    @classmethod
    def nonblank_label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Test labels must be nonblank")
        return value
