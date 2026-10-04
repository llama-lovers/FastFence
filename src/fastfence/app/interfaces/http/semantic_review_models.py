"""Bounded management-only semantic review contracts."""

from datetime import datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from fastfence.modules.control.domain.models import Policy, Snapshot
from fastfence.modules.control.domain.semantic_rules import SemanticRule
from fastfence.shared.models import StrictModel


class ReviewModel(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticCase(ReviewModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    text: str = Field(min_length=1, max_length=4096)
    direction: Literal["input", "output"]
    target: Literal["model", "tool"]
    expected: Literal["blocked", "no_semantic_block"]

    @field_validator("text")
    @classmethod
    def valid_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Case text must not be blank")
        if len(value.encode("utf-8")) > 4096:
            raise ValueError("Case text exceeds UTF-8 byte limit")
        return value


class RuleCase(SemanticCase):
    rule_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class SemanticReviewRequest(ReviewModel):
    base_version: int = Field(ge=1, strict=True)
    rule: SemanticRule
    cases: tuple[SemanticCase, ...] = Field(min_length=2, max_length=16)

    @model_validator(mode="after")
    def coverage(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Case identifiers must be unique")
        if len(
            {(case.text, case.direction, case.target) for case in self.cases}
        ) != len(self.cases):
            raise ValueError("Case text and scope must be unique")
        if any(
            not self.rule.applies_to(case.direction, case.target)
            for case in self.cases
        ):
            raise ValueError("Cases must match the rule scope")
        for direction in ("input", "output"):
            for target in ("model", "tool"):
                if self.rule.applies_to(direction, target) and {
                    case.expected
                    for case in self.cases
                    if case.direction == direction and case.target == target
                } != {"blocked", "no_semantic_block"}:
                    raise ValueError(
                        "Both expectations are required for every rule scope"
                    )
        return self


class SemanticOutcome(ReviewModel):
    status: Literal["evaluated", "not_evaluated", "error"]
    decision: Literal["blocked", "no_semantic_block"] | None = None
    semantic_score: float | None = Field(default=None, ge=0, le=1)
    latency_ms: int = Field(default=0, ge=0)
    reason: str | None = None


class SemanticCaseResult(RuleCase):
    before: SemanticOutcome
    after: SemanticOutcome
    passed: bool


class SemanticReviewView(ReviewModel):
    review_id: str | None = None
    base_version: int
    candidate_version: int
    feed_version: int
    expires_at: datetime | None = None
    model: str
    yaml_diff: str
    cases: tuple[SemanticCaseResult, ...]
    tests_passed: bool
    warnings: tuple[str, ...] = ()
    missing_rules: tuple[str, ...] = ()
    scope: Literal["semantic_only"] = "semantic_only"


class SemanticActivateRequest(ReviewModel):
    review_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{32,64}$")
    base_version: int = Field(ge=1, strict=True)
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit confirmation required")
        return value


class SemanticReceipt(ReviewModel):
    review_id: str
    subject: str
    tenant: str
    base: Snapshot
    candidate: Policy
    base_digest: str
    candidate_digest: str
    feed_digest: str
    request: SemanticReviewRequest
    cases: tuple[RuleCase, ...]
    suite_digest: str
    expires_monotonic: float
    expires_at: datetime


class SemanticReviewError(Exception):
    def __init__(self, reason: str, status: int = 409) -> None:
        super().__init__(reason)
        self.reason, self.status = reason, status
