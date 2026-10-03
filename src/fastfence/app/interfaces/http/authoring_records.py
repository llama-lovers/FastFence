from datetime import datetime
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, StrictBool, field_validator

from fastfence.modules.control.application.use_cases.policy_preview import (
    PolicySample,
    RegressionResult,
    SampleComparison,
    SampleResult,
)
from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.policy_authoring import (
    PolicyChange,
    PolicyOperation,
    PreparedPolicy,
)
from fastfence.modules.control.domain.policy_tests import GeneratedPolicyTest
from fastfence.shared.models import StrictModel

type ProposalID = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{16,64}$")]


class PolicyAuthorPort(Protocol):
    async def draft(self, request: dict[str, Any]) -> dict[str, Any]: ...


class DraftRequest(StrictModel):
    instruction: str = Field(min_length=1, max_length=8192)
    base_version: int = Field(ge=1)

    @field_validator("instruction")
    @classmethod
    def bounded_instruction(cls, value: str) -> str:
        if not value.strip() or len(value.encode()) > 8192:
            raise ValueError("Instruction must be nonblank and bounded")
        return value


class PreviewRequest(StrictModel):
    proposal_id: ProposalID
    samples: list[PolicySample] = Field(default_factory=list, max_length=16)
    tests: list[GeneratedPolicyTest] | None = Field(default=None, max_length=8)

    @field_validator("tests")
    @classmethod
    def unique_test_labels(cls, value):
        if value is not None and len({test.label for test in value}) != len(
            value
        ):
            raise ValueError("Test labels must be unique")
        return value


class ActivateRequest(StrictModel):
    proposal_id: ProposalID
    base_version: int = Field(ge=1)


class ProposalView(StrictModel):
    proposal_id: str
    base_version: int
    expires_at: datetime
    source: Literal["real_laya"] = "real_laya"
    model: str
    inference_ms: int
    operations: list[PolicyOperation]
    changes: list[PolicyChange]
    warnings: list[str]
    tests: list[GeneratedPolicyTest] = Field(default_factory=list)
    yaml_diff: str = ""


class PreviewView(ProposalView):
    results: list[SampleResult]
    comparisons: list[SampleComparison] = Field(default_factory=list)
    test_results: list[RegressionResult] = Field(default_factory=list)
    tests_passed: StrictBool = True
    feed_version: int
    scope: str = "Local content checks only; no upstream, authorization, budgets or semantic inference"


class ActivationView(StrictModel):
    tests_saved: StrictBool = False
    warnings: list[str] = Field(default_factory=list)
    proposal_id: str
    policy_version: int
    operations: list[PolicyOperation]


class WorkerResponse(StrictModel):
    proposal: dict[str, Any]
    inference_ms: int = Field(ge=0, le=300_000)
    source: Literal["real_laya"]
    model: Literal["qwen3:4b"]


class StoredProposal(StrictModel):
    proposal_id: str
    subject: str
    base_version: int
    base_policy: Policy
    expires_at: datetime
    expires_monotonic: float
    prepared: PreparedPolicy
    model: str
    inference_ms: int
    previewed: bool = False
    previewed_feed_version: int | None = None
    consumed: bool = False
    reviewed_tests: tuple[GeneratedPolicyTest, ...] = ()
    tests_passed: bool = False
    yaml_diff: str = ""

    def view(self) -> ProposalView:
        return ProposalView(
            proposal_id=self.proposal_id,
            base_version=self.base_version,
            expires_at=self.expires_at,
            model=self.model,
            inference_ms=self.inference_ms,
            operations=list(self.prepared.operations),
            changes=list(self.prepared.changes),
            warnings=list(self.prepared.warnings),
            tests=list(self.prepared.tests),
            yaml_diff=self.yaml_diff,
        )
