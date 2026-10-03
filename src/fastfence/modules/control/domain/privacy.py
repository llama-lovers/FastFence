from typing import Literal, Self

from pydantic import Field, model_validator

from fastfence.modules.control.domain.frozen import (
    FrozenControlModel,
    FrozenMap,
)

type PrivacyAction = Literal["block", "redact"]
type PrivacyDetector = Literal["pii_email", "pii_polish_id"]
type Direction = Literal["input", "output"]


class DetectorActions(FrozenControlModel):
    input: PrivacyAction | None = None
    output: PrivacyAction | None = None


class Privacy(FrozenControlModel):
    input: PrivacyAction = "block"
    output: PrivacyAction = "redact"
    enabled: bool = True
    detector_actions: FrozenMap[DetectorActions] = Field(default_factory=dict)

    @model_validator(mode="after")
    def known_detectors(self) -> Self:
        if not set(self.detector_actions).issubset(
            {"pii_email", "pii_polish_id"}
        ):
            raise ValueError("Unknown selective privacy detector")
        return self

    def action_for(self, finding: str, direction: Direction) -> PrivacyAction:
        override = self.detector_actions.get(finding)
        selected = getattr(override, direction) if override else None
        return selected or getattr(self, direction)
