"""Bounded token syntax; cryptographic verification is a separate port."""

from typing import Literal

from pydantic import ConfigDict, Field, ValidationError

from fastfence.shared.anonymization import AnonymizationError
from fastfence.shared.models import StrictModel


class TokenSpan(StrictModel):
    start: int
    end: int
    token: str = Field(repr=False, exclude=True)


class TokenFields(StrictModel):
    version: Literal["FFI1", "FFR1", "FFR2"]
    key_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,16}$")
    rule_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    prefix: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    identifier: str = Field(pattern=r"^[a-zA-Z0-9_-]{22}$")
    expiry: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,11}$")
    payload: str = Field(
        min_length=1,
        max_length=12000,
        pattern=r"^[a-zA-Z0-9_-]+$",
        repr=False,
        exclude=True,
    )


class VerifiedToken(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    original: str | None = Field(default=None, repr=False, exclude=True)
    rule_id: str
    identifier: str
    mode: Literal["irreversible", "reversible"]


def token_spans(
    text: str, *, max_token_bytes: int = 16384, max_tokens: int = 256
) -> list[TokenSpan]:
    found: list[TokenSpan] = []
    position = 0
    while (start := text.find("[", position)) >= 0:
        if text[start : start + 3].lower() != "[ff":
            position = start + 1
            continue
        end = text.find("]", start)
        if end < 0:
            raise AnonymizationError("anonymization_invalid_token")
        token = text[start : end + 1]
        if len(token.encode()) > max_token_bytes:
            raise AnonymizationError("anonymization_token_too_large")
        if len(found) >= max_tokens:
            raise AnonymizationError("anonymization_capacity")
        found.append(TokenSpan(start=start, end=end + 1, token=token))
        position = end + 1
    return found


def parse_token(token: str) -> TokenFields:
    try:
        if not token.startswith("[FF") or not token.endswith("]"):
            raise ValueError
        parts = token[1:-1].split(".")
        if len(parts) == 6 and parts[0] == "FFI1":
            version = "FFI1"
            expiry = None
        elif len(parts) == 7 and parts[0] in {"FFR1", "FFR2"}:
            version = "FFR1" if parts[0] == "FFR1" else "FFR2"
            expiry = parts[5]
        else:
            raise ValueError
        return TokenFields(
            version=version,
            key_id=parts[1],
            rule_id=parts[2],
            prefix=parts[3],
            identifier=parts[4],
            expiry=expiry,
            payload=parts[-1],
        )
    except (ValueError, ValidationError):
        raise AnonymizationError("anonymization_invalid_token") from None
