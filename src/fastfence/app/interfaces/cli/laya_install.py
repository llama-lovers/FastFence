"""Install the reviewed Laya helpers from a wheel without a source checkout."""

import hashlib
import os
import shutil
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from fastfence.app.interfaces.cli.bootstrap_config import _create_exclusive

LAYA_FILES = (
    "setup.sh",
    "semantic_worker.py",
    "semantic_response.py",
    "authoring_contracts.py",
    "policy_generation.py",
    "draft_policy.py",
    "author_rule.py",
    "run_demo.py",
)


PREVIOUS_SETUP_SHA256 = "b992a7fa7457afd6f1c883fbbad2a5a62d9ec48599441efa8f37d9d4db7e6a5f"  # pragma: allowlist secret - public released installer hash


def _reviewed_upgrade(path: Path) -> bool:
    return (
        path.name == "setup.sh"
        and not path.is_symlink()
        and path.is_file()
        and hashlib.sha256(path.read_bytes()).hexdigest()
        == PREVIOUS_SETUP_SHA256
    )


def _upgrade_setup(path: Path, content: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=".setup-upgrade-", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if not _reviewed_upgrade(path):
            raise ValueError(
                "Existing Laya installer changed during upgrade; existing files were preserved."
            )
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def stage_laya(root: Path) -> Path:
    bundle = files("fastfence.shared").joinpath("laya_bundle")
    development = Path(__file__).resolve().parents[5] / "integrations/laya"
    contents = {
        name: bundle.joinpath(name).read_bytes()
        if bundle.is_dir()
        else (development / name).read_bytes()
        for name in LAYA_FILES
    }
    destination = root / "integrations/laya"
    for name, content in contents.items():
        path = destination / name
        if path.is_symlink() or (
            path.exists()
            and path.read_bytes() != content
            and not _reviewed_upgrade(path)
        ):
            raise ValueError(
                "Existing Laya helper files differ from this package; preserve your changes and choose a new FASTFENCE_AUTHORING_ROOT."
            )
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in contents.items():
        path = destination / name
        if not path.exists():
            _create_exclusive(path, content)
        elif path.read_bytes() != content:
            _upgrade_setup(path, content)
    return destination / "setup.sh"


def setup_laya(root: Path) -> None:
    if any(shutil.which(name) is None for name in ("git", "uv", "sh")):
        raise SystemExit(
            "Laya setup requires git, sh and uv. Install Git and run `python -m pip install uv`, then retry `fastfence setup-laya`."
        )
    try:
        script = stage_laya(root)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    try:
        result = subprocess.run(
            ["sh", str(script)], cwd=root, check=False, timeout=900
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "Laya setup exceeded 15 minutes; check connectivity and rerun `fastfence init`."
        ) from None
    if result.returncode:
        raise SystemExit(
            "Laya setup failed; resolve the installer error and retry."
        )
    print(
        "Laya installed. The configured semantic assessor and business models are managed independently."
    )
