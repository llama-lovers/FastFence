"""Shared pseudonymization contracts, independent of feature modules."""

import hashlib
import json
from typing import Any, Literal, Self

import re2
from pydantic import ConfigDict, Field, PrivateAttr, StrictBool, model_validator

from fastfence.shared.models import StrictModel

type AnonymizationDirection = Literal["input", "output"]
type AnonymizationTarget = Literal["model", "tool"]


class _ImmutableModel(StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        revalidate_instances="always",
    )


class AnonymizationRule(_ImmutableModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    operator: Literal["literal", "regex"]
    value: str = Field(min_length=1, max_length=256)
    replacement: str = Field(
        default="ANONIM", pattern=r"^[A-Z][A-Z0-9_]{0,31}$"
    )
    case_sensitive: StrictBool = True
    direction: Literal["input", "output", "both"] = "both"
    target: Literal["model", "tool", "all"] = "all"
    allow_restore: StrictBool = False
    _compiled: Any = PrivateAttr(default=None)
    _fingerprint: str = PrivateAttr(default="")

    @model_validator(mode="after")
    def prepare(self) -> Self:
        if not self.value.strip():
            raise ValueError("Anonymization patterns must not be blank")
        options = re2.Options()
        options.case_sensitive = self.case_sensitive
        options.log_errors = False
        options.max_mem = 1024 * 1024
        pattern = (
            re2.escape(self.value) if self.operator == "literal" else self.value
        )
        try:
            compiled = re2.compile(pattern, options=options)
            samples = ("", "a", "0", " ", "\n", "abc xyz", "λ", "a\n0")
            if any(
                match.start() == match.end()
                for sample in samples
                for match in compiled.finditer(sample)
            ):
                raise ValueError("Anonymization patterns must consume text")
        except Exception:
            raise ValueError("Unsupported anonymization pattern") from None
        content = self.model_dump(mode="json", exclude={"allow_restore"})
        fingerprint = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        private = self.__pydantic_private__
        assert private is not None
        private["_compiled"] = compiled
        private["_fingerprint"] = fingerprint
        return self

    @property
    def compiled(self) -> Any:
        return self._compiled

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def __eq__(self, other: object) -> bool:
        # Compiled objects are caches, not part of policy identity.
        return (
            isinstance(other, AnonymizationRule)
            and self.fingerprint == other.fingerprint
            and self.allow_restore == other.allow_restore
        )

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_compiled", "_fingerprint"}:
            raise TypeError("Prepared anonymization rule is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in {"_compiled", "_fingerprint"}:
            raise TypeError("Prepared anonymization rule is immutable")
        super().__delattr__(name)


class AnonymizationConfig(_ImmutableModel):
    enabled: StrictBool = False
    mode: Literal["irreversible", "reversible"] = "irreversible"
    rules: tuple[AnonymizationRule, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Anonymization rule IDs must be unique")
        return self


class AnonymizationContext(_ImmutableModel):
    tenant: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    subject: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")


class AnonymizationResult(StrictModel):
    value: Any
    findings: list[str] = Field(default_factory=list)
    changed: bool = False


class AnonymizationError(Exception):
    """Only static reasons leave the stateless module."""

    def __init__(self, reason: str) -> None:
        allowed = {
            "anonymization_capacity",
            "anonymization_value_too_large",
            "anonymization_ambiguous_alias",
            "anonymization_empty_match",
            "anonymization_restore_denied",
            "anonymization_invalid_token",
            "anonymization_token_expired",
            "anonymization_token_too_large",
            "anonymization_unavailable",
        }
        self.reason = (
            reason if reason in allowed else "anonymization_unavailable"
        )
        super().__init__(self.reason)
