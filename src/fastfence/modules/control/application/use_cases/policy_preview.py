from typing import Literal

from pydantic import Field

from fastfence.modules.control.application.services.inspection import (
    inspect_payload,
)
from fastfence.modules.control.contracts.ports import SecretsPort
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import Snapshot
from fastfence.shared.models import StrictModel


class PolicySample(StrictModel):
    target: Literal["model", "tool"] = "model"
    direction: Literal["input", "output"] = "input"
    text: str = Field(max_length=4096)


class SampleResult(StrictModel):
    index: int
    decision: Literal["blocked", "redacted", "no_local_match"]
    reason: str
    findings: list[str]
    safe_text: str | None = None


def preview_sample(
    snapshot: Snapshot,
    sample: PolicySample,
    index: int,
    secrets: SecretsPort | None,
) -> SampleResult:
    key = (
        "prompt"
        if sample.target == "model" and sample.direction == "input"
        else "text"
    )
    try:
        safe, findings = inspect_payload(
            {key: sample.text},
            snapshot,
            sample.direction,
            secrets,
            target=sample.target,
        )
        return SampleResult(
            index=index,
            decision="redacted" if findings else "no_local_match",
            reason="sensitive_data_redacted" if findings else "no_local_match",
            findings=findings,
            safe_text=safe[key],
        )
    except RejectedError as error:
        return SampleResult(
            index=index,
            decision="blocked",
            reason=error.reason,
            findings=error.findings,
        )
