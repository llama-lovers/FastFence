from typing import Literal, Protocol

from fastfence.modules.anonymization.domain.tokens import VerifiedToken
from fastfence.shared.anonymization import (
    AnonymizationContext,
    AnonymizationRule,
)


class TokenPort(Protocol):
    def issue(
        self,
        rule: AnonymizationRule,
        original: str,
        context: AnonymizationContext,
        mode: Literal["irreversible", "reversible"],
    ) -> str: ...

    def verify(
        self,
        token: str,
        rule: AnonymizationRule,
        context: AnonymizationContext,
    ) -> VerifiedToken: ...
