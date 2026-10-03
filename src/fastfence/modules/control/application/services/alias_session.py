"""Control-side integration depends only on the pseudonymization port."""

from typing import Any, Literal

from fastfence.modules.control.contracts.ports import AnonymizationPort
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import InvocationState, ToolCall
from fastfence.shared.anonymization import (
    AnonymizationContext,
    AnonymizationError,
)


class AliasSession:
    def __init__(self, state: InvocationState, port: AnonymizationPort | None):
        self.state, self.port = state, port
        self.config = state.snapshot.policy.anonymization
        self.target: Literal["model", "tool"] = (
            "tool" if isinstance(state.call, ToolCall) else "model"
        )

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.config.rules)

    def validate_restore(self) -> None:
        if self.state.call.restore_originals and (
            not self.enabled
            or self.config.mode != "reversible"
            or not any(rule.allow_restore for rule in self.config.rules)
        ):
            raise RejectedError("anonymization_restore_denied")

    def context(self) -> AnonymizationContext:
        return AnonymizationContext(
            tenant=self.state.identity.tenant,
            subject=self.state.identity.subject,
        )

    def mask(
        self, value: Any, direction: Literal["input", "output"]
    ) -> tuple[Any, list[str]]:
        if self.port is None:
            raise RejectedError("anonymization_unavailable")
        try:
            result = self.port.transform(
                value,
                context=self.context(),
                config=self.config,
                direction=direction,
                target=self.target,
            )
        except AnonymizationError as error:
            raise RejectedError(error.reason) from None
        self.state.verdict.anonymized |= result.changed
        return result.value, [
            "anonymization_" + name for name in result.findings
        ]

    def reveal(self, value: Any) -> Any:
        if self.port is None:
            if self.enabled:
                raise RejectedError("anonymization_unavailable")
            return value
        try:
            return self.port.reveal_for_checks(
                value,
                context=self.context(),
                config=self.config,
                target=self.target,
            ).value
        except AnonymizationError as error:
            raise RejectedError(error.reason) from None

    def restore(self, value: Any) -> Any:
        if self.port is None:
            raise RejectedError("anonymization_unavailable")
        try:
            result = self.port.restore(
                value,
                context=self.context(),
                config=self.config,
                target=self.target,
            )
        except AnonymizationError as error:
            raise RejectedError(error.reason) from None
        self.state.verdict.restored = result.changed
        self.state.findings.update(
            "restoration_" + name for name in result.findings
        )
        return result.value
