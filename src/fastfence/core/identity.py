from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from fastfence.core.schema import Identity


class IdentityStore:
    """Locally provisioned tokens bind a caller to trusted server-side claims."""

    def __init__(self, path: Path):
        records = json.loads(path.read_text())
        self._records = [
            (r["token_sha256"], Identity.model_validate(r["identity"])) for r in records
        ]
        if not self._records:
            raise ValueError("No credentials provisioned; run fastfence init")
        if len({i.subject for _, i in self._records}) != len(self._records):
            raise ValueError("Identity subjects must be unique")
        if len({h for h, _ in self._records}) != len(self._records):
            raise ValueError("Credential hashes must be unique")

    def authenticate(self, token: str | None) -> Identity | None:
        digest = hashlib.sha256((token or "").encode()).hexdigest()
        for expected, identity in self._records:
            if token and hmac.compare_digest(digest, expected):
                return identity.model_copy(deep=True)
        return None

    def by_subject(self, subject: str) -> Identity | None:
        return next(
            (i.model_copy(deep=True) for _, i in self._records if i.subject == subject), None
        )
