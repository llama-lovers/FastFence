from __future__ import annotations

import hashlib
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
    records: list[CredentialRecord] = Field(min_length=1, max_length=65_536)


class CredentialLimits(StrictModel):
    max_records: int = Field(default=4096, ge=1, le=65_536)
    max_bytes: int = Field(default=1_048_576, ge=1024, le=67_108_864)


class IdentityStore:
    """Locally provisioned tokens bind a caller to trusted server-side claims."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        records: list[dict[str, Any]] | None = None,
        json_content: str | None = None,
        max_records: int = 4096,
        max_bytes: int = 1_048_576,
    ) -> None:
        limits = CredentialLimits(max_records=max_records, max_bytes=max_bytes)
        if (
            sum(source is not None for source in (records, path, json_content))
            != 1
        ):
            raise ValueError("Choose exactly one trusted credential source")
        if records is None:
            if json_content is not None:
                raw = json_content.encode("utf-8")
            else:
                assert path is not None
                with path.open("rb") as stream:
                    raw = stream.read(limits.max_bytes + 1)
            if len(raw) > limits.max_bytes:
                raise ValueError("Credential configuration is too large")
            records = json.loads(raw)
        if isinstance(records, list) and len(records) > limits.max_records:
            raise ValueError("Credential record limit exceeded")
        validated = CredentialSet.model_validate({"records": records})
        self._records = tuple(
            (record.token_sha256, record.identity)
            for record in validated.records
        )
        if len({i.subject for _, i in self._records}) != len(self._records):
            raise ValueError("Identity subjects must be unique")
        if len({h for h, _ in self._records}) != len(self._records):
            raise ValueError("Credential hashes must be unique")
        self._by_digest = dict(self._records)
        self._by_subject = {
            identity.subject: identity for _, identity in self._records
        }

    def authenticate(self, token: str | None) -> Identity | None:
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        return self._by_digest.get(digest)

    def by_subject(self, subject: str) -> Identity | None:
        return self._by_subject.get(subject)
