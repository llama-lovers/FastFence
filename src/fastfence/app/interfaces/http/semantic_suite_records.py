"""Private reviewed semantic cases and their last verified policy provenance."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fastfence.app.interfaces.http.semantic_review_models import (
    RuleCase,
    SemanticCase,
    SemanticReviewRequest,
)
from fastfence.modules.control.domain.semantic_rules import SemanticRule


class SuiteRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SavedSemanticSuite(SuiteRecord):
    rule: SemanticRule
    policy_version: int = Field(ge=1)
    policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: Literal["laya"] = "laya"
    model: str = Field(min_length=1, max_length=100)
    threshold: float = Field(ge=0, le=1)
    cases: tuple[RuleCase, ...] = Field(min_length=2, max_length=16)

    @model_validator(mode="after")
    def consistent_cases(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        if any(case.rule_id != self.rule.id for case in self.cases):
            raise ValueError("Case belongs to another rule")
        SemanticReviewRequest(
            base_version=self.policy_version,
            rule=self.rule,
            cases=tuple(
                SemanticCase.model_validate(
                    case.model_dump(exclude={"rule_id"})
                )
                for case in self.cases
            ),
        )
        return self


class SemanticSuiteFile(SuiteRecord):
    schema_version: Literal[1] = 1
    suites: tuple[SavedSemanticSuite, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def bounded_unique_suites(self) -> Self:
        if len({suite.rule.id for suite in self.suites}) != len(self.suites):
            raise ValueError("Duplicate rule suites")
        if sum(len(suite.cases) for suite in self.suites) > 64:
            raise ValueError("Too many stored cases")
        return self


class SuiteSnapshot(SuiteRecord):
    document: SemanticSuiteFile
    digest: str


class MergedSemanticCases(SuiteRecord):
    cases: tuple[RuleCase, ...] = Field(max_length=64)
    warnings: tuple[str, ...] = ()
    missing_rules: tuple[str, ...] = ()


class PreparedSuiteWrite(SuiteRecord):
    content: bytes = Field(max_length=65_536)
    expected_digest: str
