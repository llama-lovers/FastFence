"""Initialize reviewed configuration resources without replacing operator files."""

import json
import os
import tempfile
from importlib.resources import files
from pathlib import Path

import yaml

from fastfence.modules.control.domain.models import Snapshot


class ConfigurationInitializationError(ValueError):
    """A configuration cannot safely be initialized."""


def _read_existing(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ConfigurationInitializationError(
            "Configuration exceeds the configured size limit; existing files were preserved."
        )
    return content


def _create_exclusive(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=".initialize-", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Publish only a complete file. A concurrent initializer cannot overwrite it.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def initialize_config(root: Path, *, max_source_bytes: int = 262_144) -> None:
    """Validate existing configuration and exclusively create missing defaults.

    This works from an installed wheel; a source checkout is not required.
    Errors deliberately omit the invalid configuration and validation payload.
    """
    directory = root / "config"
    resources = files("fastfence.shared.defaults")
    contents: dict[str, bytes] = {}
    missing: list[str] = []
    for name in ("policy.yaml", "signatures.json"):
        path = directory / name
        if path.exists():
            contents[name] = _read_existing(path, max_source_bytes)
        else:
            contents[name] = resources.joinpath(name).read_bytes()
            missing.append(name)
        if len(contents[name]) > max_source_bytes:
            raise ConfigurationInitializationError(
                "Configuration exceeds the configured size limit; existing files were preserved."
            )
    try:
        Snapshot.model_validate(
            {
                "policy": yaml.safe_load(contents["policy.yaml"]),
                "feed": json.loads(contents["signatures.json"]),
            }
        )
    except (ValueError, yaml.YAMLError, RecursionError):
        raise ConfigurationInitializationError(
            "Invalid configuration in config/policy.yaml or config/signatures.json; "
            "repair those files and rerun fastfence init. Existing files were preserved."
        ) from None
    directory.mkdir(parents=True, exist_ok=True)
    for name in missing:
        _create_exclusive(directory / name, contents[name])
