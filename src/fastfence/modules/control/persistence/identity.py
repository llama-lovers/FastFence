from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from pydantic import Field

from fastfence.modules.control.domain.models import Identity
from fastfence.shared.models import StrictModel


class CredentialRecord(StrictModel):
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity: Identity


class CredentialSet(StrictModel):
    records: list[CredentialRecord] = Field(min_length=1, max_length=4096)


class IdentityStore:
    """Locally provisioned tokens bind a caller to trusted server-side claims."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        records: list[dict[str, Any]] | None = None,
    ) -> None:
        if records is not None and path is not None:
            raise ValueError("Choose one trusted credential source")
        if records is None:
            if path is None:
                raise ValueError("Trusted credentials are required at startup")
            with path.open("rb") as stream:
                raw = stream.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ValueError("Credential configuration is too large")
            records = json.loads(raw)
        validated = CredentialSet.model_validate({"records": records})
        self._records = tuple(
            (record.token_sha256, record.identity)
            for record in validated.records
        )
        if len({i.subject for _, i in self._records}) != len(self._records):
            raise ValueError("Identity subjects must be unique")
        if len({h for h, _ in self._records}) != len(self._records):
            raise ValueError("Credential hashes must be unique")
        self._by_subject = {
            identity.subject: identity for _, identity in self._records
        }

    def authenticate(self, token: str | None) -> Identity | None:
        digest = hashlib.sha256((token or "").encode()).hexdigest()
        for expected, identity in self._records:
            if token and hmac.compare_digest(digest, expected):
                return identity
        return None

    def by_subject(self, subject: str) -> Identity | None:
        return self._by_subject.get(subject)
