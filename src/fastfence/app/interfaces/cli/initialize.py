"""Explicit local credential provisioning; repeat runs never rotate secrets."""

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from fastfence.modules.control.domain.models import Identity
from fastfence.shared.settings.app_settings import AppSettings
from fastfence.workflows.anonymization import build_anonymization


class InitialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity: Identity


def _validate_links(records: list[InitialRecord], tokens: dict) -> None:
    subjects = [record.identity.subject for record in records]
    if len(set(subjects)) != len(subjects) or set(tokens) != set(subjects):
        raise ValueError
    for record in records:
        token = tokens[record.identity.subject]
        if not isinstance(token, str) or not token:
            raise ValueError
        if hashlib.sha256(token.encode()).hexdigest() != record.token_sha256:
            raise ValueError


def _validate_existing(state: Path) -> bool:
    identities, credentials = (
        state / "identities.json",
        state
        / (
            "credentials.json"
            if (state / "credentials.json").exists()
            else "demo-tokens.json"
        ),
    )
    if (state / "credentials.json").exists() and (
        state / "demo-tokens.json"
    ).exists():
        raise SystemExit(
            "Initialization refused: ambiguous credential files. Existing files were preserved."
        )
    if not identities.exists() and not credentials.exists():
        return False
    try:
        raw = json.loads(identities.read_text())
        tokens = json.loads(credentials.read_text())
        records = [InitialRecord.model_validate(item) for item in raw]
        if not records or not isinstance(tokens, dict):
            raise ValueError
        if len({record.token_sha256 for record in records}) != len(records):
            raise ValueError
        _validate_links(records, tokens)
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit(
            "Initialization refused: partial or invalid credential state. "
            "Existing files were preserved. Restore the matching identities.json "
            "and credentials.json (or legacy demo-tokens.json) backup, or choose a new directory with --state."
        ) from None
    return True


def _write_private(path: Path, data: object) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(data, file, indent=2)
        file.write("\n")


def initialize(state: Path) -> None:
    if _validate_existing(state):
        print(f"Already initialized: {state}. Existing credentials preserved.")
        return
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    records, tokens = [], {}
    for subject, tenant, roles, admin in [
        ("local-agent", "local", ["analyst"], False),
        ("local-admin", "management", [], True),
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
    _write_private(state / "credentials.json", tokens)
    print(
        f"Initialized {state}. Credentials: {state / 'credentials.json'} (private, gitignored)."
    )
    print(
        "Dashboard: connect local-admin to manage policies; use local-agent to make protected requests."
    )


def initialize_keys(path: Path, key_id: str) -> None:
    if path.exists():
        build_anonymization(
            AppSettings(
                anonymization_keys_file=path, anonymization_key_id=key_id
            )
        ).close()
        print(f"Anonymization keyring preserved: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_private(
        path, {key_id: base64.b64encode(secrets.token_bytes(32)).decode()}
    )
    print(f"Private anonymization keyring created: {path} (mode 0600).")


def initialize_anonymization(settings: AppSettings) -> None:
    if settings.anonymization_keys_json is not None:
        build_anonymization(settings).close()
        print(
            "Existing environment anonymization keyring validated and preserved."
        )
        return
    initialize_keys(
        settings.anonymization_keys_file
        or settings.state_path / "anonymization-keys.json",
        settings.anonymization_key_id,
    )
