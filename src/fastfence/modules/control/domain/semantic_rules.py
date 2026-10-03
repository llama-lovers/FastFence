"""Named natural-language prohibitions with explicit enforcement scope."""

from typing import Literal

from pydantic import Field, field_validator

from fastfence.modules.control.domain.frozen import FrozenControlModel


class SemanticRule(FrozenControlModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    instruction: str = Field(min_length=1, max_length=2048)
    direction: Literal["input", "output", "both"] = "both"
    target: Literal["model", "tool", "all"] = "all"

    @field_validator("instruction")
    @classmethod
    def nonblank_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Semantic rule instruction must not be blank")
        return value

    def applies_to(
        self,
        direction: Literal["input", "output"],
        target: Literal["model", "tool"],
    ) -> bool:
        return self.direction in {direction, "both"} and self.target in {
            target,
            "all",
        }
