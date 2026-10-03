"""Private key file provisioning and startup precedence."""

import base64
import json

import pytest

from fastfence.app.interfaces.cli.initialize import initialize_keys
from fastfence.shared.settings.app_settings import AppSettings
from fastfence.workflows.anonymization import build_anonymization


def test_default_private_key_file_is_discovered(tmp_path):
    path = tmp_path / "state/anonymization-keys.json"
    initialize_keys(path, "local-v1")
    workflow = build_anonymization(AppSettings(root=tmp_path))
    assert workflow.runtime is not None


def test_explicit_json_precedes_implicit_file(tmp_path):
    path = tmp_path / "state/anonymization-keys.json"
    path.parent.mkdir()
    path.write_text("invalid file should not be loaded")
    settings = AppSettings(
        root=tmp_path,
        anonymization_keys_json=json.dumps(
            {"local-v1": base64.b64encode(bytes(range(32))).decode()}
        ),
    )
    assert build_anonymization(settings).runtime is not None


def test_explicit_ambiguous_key_sources_are_rejected(tmp_path):
    settings = AppSettings(
        root=tmp_path,
        anonymization_keys_file=tmp_path / "keys",
        anonymization_keys_json="{}",
    )
    with pytest.raises(ValueError, match="Choose one"):
        build_anonymization(settings)


@pytest.mark.parametrize(
    "data",
    [
        None,
        "not-json-private",
        "{}",
        '{"local-v1":"invalid-private-base64"}',
        "x" * 65537,
    ],
)
def test_missing_or_invalid_explicit_key_file_is_safe(tmp_path, data):
    path = tmp_path / "keys"
    if data is not None:
        path.write_text(data)
    with pytest.raises(ValueError) as caught:
        build_anonymization(
            AppSettings(root=tmp_path, anonymization_keys_file=path)
        )
    assert "private" not in str(caught.value).lower().replace(
        "private anonymization", ""
    )


def test_invalid_existing_keyring_is_not_replaced(tmp_path):
    path = tmp_path / "keys"
    path.write_text("invalid-key-material")
    with pytest.raises(ValueError):
        initialize_keys(path, "local-v1")
    assert path.read_text() == "invalid-key-material"
