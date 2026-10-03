import json
from importlib.resources import files
from pathlib import Path

import pytest
import yaml

from fastfence.app.interfaces.cli.bootstrap_config import (
    ConfigurationInitializationError,
    _create_exclusive,
    initialize_config,
)
from fastfence.modules.control.domain.models import Snapshot


def test_empty_root_receives_valid_offline_configuration(
    tmp_path: Path,
) -> None:
    initialize_config(tmp_path)
    config = tmp_path / "config"
    snapshot = Snapshot.model_validate(
        {
            "policy": yaml.safe_load((config / "policy.yaml").read_bytes()),
            "feed": json.loads((config / "signatures.json").read_bytes()),
        }
    )
    assert snapshot.policy.semantic.provider == "disabled"
    assert snapshot.policy.privacy.input == "block"
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("name", ["policy.yaml", "signatures.json"])
def test_existing_file_is_preserved_and_missing_file_created(
    tmp_path: Path, name: str
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    content = files("fastfence.shared.defaults").joinpath(name).read_bytes()
    content = content.replace(b"version: 1", b"version: 15").replace(
        b'"version": 2', b'"version": 15'
    )
    (config / name).write_bytes(content)
    initialize_config(tmp_path)
    initialize_config(tmp_path)
    assert (config / name).read_bytes() == content
    assert (config / "policy.yaml").is_file()
    assert (config / "signatures.json").is_file()


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("policy.yaml", b"version: broken\nprivate: never-show-this"),
        ("policy.yaml", b"malformed: ["),
        ("signatures.json", b'{"private":"never-show-this"}'),
        ("signatures.json", b"not-json"),
    ],
)
def test_invalid_partial_configuration_is_rejected_without_writes(
    tmp_path: Path, name: str, content: bytes
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / name).write_bytes(content)
    with pytest.raises(ConfigurationInitializationError) as error:
        initialize_config(tmp_path)
    assert "never-show-this" not in str(error.value)
    assert list(config.iterdir()) == [config / name]
    assert (config / name).read_bytes() == content


def test_existing_configuration_is_bounded_before_parsing(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "policy.yaml").write_bytes(b" " * 262_145)
    with pytest.raises(ConfigurationInitializationError, match="size limit"):
        initialize_config(tmp_path)
    assert not (config / "signatures.json").exists()


def test_defaults_obey_configured_size_limit(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationInitializationError, match="size limit"):
        initialize_config(tmp_path, max_source_bytes=10)
    assert not (tmp_path / "config").exists()


def test_atomic_publication_never_overwrites_existing_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "policy.yaml"
    destination.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        _create_exclusive(destination, b"replacement")
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize(
    ("resource", "source"),
    [
        ("policy.yaml", "policy.offline.yaml"),
        ("signatures.json", "signatures.json"),
    ],
)
def test_packaged_defaults_match_reviewed_repository_configuration(
    resource: str, source: str
) -> None:
    root = Path(__file__).resolve().parents[2]
    assert (
        files("fastfence.shared.defaults").joinpath(resource).read_bytes()
        == (root / "config" / source).read_bytes()
    )
