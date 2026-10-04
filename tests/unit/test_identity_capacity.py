"""Registry capacity does not change caller isolation or credential validity."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from fastfence.app.factory import create_app
from fastfence.modules.control.persistence.identity import IdentityStore
from fastfence.shared.settings.app_settings import AppSettings


def records(count):
    return [
        {
            "token_sha256": hashlib.sha256(
                f"test-registry-{index}".encode()
            ).hexdigest(),
            "identity": {
                "subject": f"user-{index}",
                "tenant": f"tenant-{index % 10}",
                "roles": ["analyst"],
            },
        }
        for index in range(count)
    ]


def test_index_preserves_isolation_and_rejects_invalid_credentials():
    store = IdentityStore(records=records(4096))
    for index in (0, 15, 2048, 4095):
        identity = store.authenticate(f"test-registry-{index}")
        assert identity is not None
        assert identity.subject == f"user-{index}"
        assert identity.tenant == f"tenant-{index % 10}"
        assert store.by_subject(identity.subject) is identity
    for token in (None, "", "test-registry-4096", "test-registry-4095 "):
        assert store.authenticate(token) is None


def test_default_record_limit_retained_and_explicit_capacity_accepts_5000():
    data = records(5000)
    with pytest.raises(ValueError, match="record limit"):
        IdentityStore(records=data)
    store = IdentityStore(records=data, max_records=5000)
    assert store.authenticate("test-registry-4999").subject == "user-4999"
    with pytest.raises(ValueError, match="record limit"):
        IdentityStore(records=data, max_records=4999)


@pytest.mark.parametrize("source", ["file", "inline"])
def test_sources_obey_exact_byte_bound(tmp_path, source):
    content = json.dumps(records(10))
    raw = content.encode()
    path = tmp_path / "identities.json"
    path.write_bytes(raw)
    kwargs = {"path": path} if source == "file" else {"json_content": content}
    assert IdentityStore(**kwargs, max_bytes=len(raw)).authenticate(
        "test-registry-9"
    )
    with pytest.raises(ValueError, match="too large"):
        IdentityStore(**kwargs, max_bytes=len(raw) - 1)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_records", 0),
        ("max_records", 65537),
        ("max_bytes", 1023),
        ("max_bytes", 67108865),
    ],
)
def test_registry_limits_are_bounded(field, value):
    with pytest.raises(ValidationError):
        IdentityStore(records=records(1), **{field: value})


@pytest.mark.parametrize("field", ["token_sha256", "identity"])
def test_duplicate_credentials_or_subjects_are_rejected(field):
    data = records(2)
    data[1][field] = data[0][field]
    with pytest.raises(ValueError, match="unique"):
        IdentityStore(records=data)


def test_capacity_settings_reach_runtime(project):
    app = create_app(
        AppSettings(
            root=project,
            identity_config_json=json.dumps(records(5000)),
            identity_max_records=5000,
            identity_max_source_bytes=4_194_304,
        )
    )
    try:
        assert (
            app.state.runtime.authenticate("test-registry-4999").subject
            == "user-4999"
        )
    finally:
        app.state.runtime.close()
