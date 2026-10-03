"""Pure local comparison with explicit limitations and stateless transformations."""

from fastfence.modules.control.application.services.inspection import (
    inspect_payload,
)
from fastfence.modules.control.contracts.ports import (
    AnonymizationPort,
    SecretsPort,
)
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import Identity, Snapshot
from fastfence.modules.control.domain.policy_tests import (
    GeneratedPolicyTest,
    LocalDecision,
    PolicySample,
)
from fastfence.shared.anonymization import (
    AnonymizationContext,
    AnonymizationError,
)
from fastfence.shared.models import StrictModel


class SampleResult(StrictModel):
    index: int
    decision: LocalDecision
    reason: str
    findings: list[str]
    safe_text: str | None = None


class SampleComparison(StrictModel):
    index: int
    before: SampleResult
    after: SampleResult
    changed: bool
    safe_text_changed: bool


class RegressionResult(StrictModel):
    test: GeneratedPolicyTest
    comparison: SampleComparison
    passed: bool


def preview_sample(
    snapshot: Snapshot,
    sample: PolicySample,
    index: int,
    secrets: SecretsPort | None,
    *,
    anonymization: AnonymizationPort | None = None,
    identity: Identity | None = None,
) -> SampleResult:
    key = (
        "prompt"
        if sample.target == "model" and sample.direction == "input"
        else "text"
    )
    context = AnonymizationContext(
        tenant=identity.tenant if identity is not None else "preview",
        subject=identity.subject
        if identity is not None
        else "synthetic-preview",
    )

    def mask(value):
        if anonymization is None:
            raise RejectedError("anonymization_unavailable")
        result = anonymization.transform(
            value,
            context=context,
            config=snapshot.policy.anonymization,
            direction=sample.direction,
            target=sample.target,
        )
        return result.value, [
            "anonymization_" + finding for finding in result.findings
        ]

    def reveal(value):
        if anonymization is None:
            if snapshot.policy.anonymization.enabled or "[FF" in sample.text:
                raise RejectedError("anonymization_unavailable")
            return value
        return anonymization.reveal_for_checks(
            value,
            context=context,
            config=snapshot.policy.anonymization,
            target=sample.target,
        ).value

    try:
        safe, findings = inspect_payload(
            {key: sample.text},
            snapshot,
            sample.direction,
            secrets,
            target=sample.target,
            anonymize=mask if snapshot.policy.anonymization.enabled else None,
            reveal=reveal,
        )
        return SampleResult(
            index=index,
            decision="redacted" if findings else "no_local_match",
            reason="sensitive_data_redacted" if findings else "no_local_match",
            findings=findings,
            safe_text=safe[key],
        )
    except (RejectedError, AnonymizationError) as error:
        return SampleResult(
            index=index,
            decision="blocked",
            reason=error.reason,
            findings=error.findings if isinstance(error, RejectedError) else [],
        )


def compare_sample(
    base: Snapshot,
    candidate: Snapshot,
    sample: PolicySample,
    index: int,
    secrets: SecretsPort | None,
    anonymization: AnonymizationPort | None = None,
) -> SampleComparison:
    before = preview_sample(
        base, sample, index, secrets, anonymization=anonymization
    )
    after = preview_sample(
        candidate, sample, index, secrets, anonymization=anonymization
    )
    return SampleComparison(
        index=index,
        before=before,
        after=after,
        changed=(before.decision, before.reason, before.findings)
        != (after.decision, after.reason, after.findings),
        safe_text_changed=before.safe_text != after.safe_text,
    )
