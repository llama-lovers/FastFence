"""Provision synthetic tenants only for explicit examples and tests."""

import hashlib
import secrets
from pathlib import Path

from fastfence.app.interfaces.cli.initialize import (
    _validate_existing,
    _write_private,
)


def initialize(state: Path) -> None:
    if _validate_existing(state):
        print(f"Already initialized: {state}. Existing credentials preserved.")
        return
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    records, tokens = [], {}
    for subject, tenant, roles, admin in [
        ("analyst-blue", "blue", ["analyst"], False),
        ("operator-blue", "blue", ["operator"], False),
        ("analyst-green", "green", ["analyst"], False),
        ("security-admin", "management", [], True),
    ]:
        token = secrets.token_urlsafe(32)
        tokens[subject] = token
        records.append(
            {
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "identity": {
                    "subject": subject,
                    "tenant": tenant,
                    "roles": roles,
                    "admin": admin,
                },
            }
        )
    _write_private(state / "identities.json", records)
    _write_private(state / "demo-tokens.json", tokens)
    print(
        f"Initialized {state}. Credentials: {state / 'demo-tokens.json'} (private, gitignored)."
    )
    print(
        "Dashboard: copy analyst-blue and security-admin tokens into Connect."
    )
