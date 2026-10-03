"""Exercise the installer with real local Git objects and no network or packages."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from fastfence.app.interfaces.cli import laya_install

REPO = Path(__file__).resolve().parents[2]
PREVIOUS = REPO / "tests/test_data/laya/setup-v1.0.1.sh"


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def fixture_remote(tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    git(remote, "init")
    git(remote, "config", "user.name", "Fixture")
    git(remote, "config", "user.email", "fixture@example.invalid")
    git(remote, "config", "uploadpack.allowFilter", "true")
    (remote / "engine").mkdir()
    (remote / "engine/requirements.lock").write_text("# synthetic lock\n")
    (remote / "engine/runtime.py").write_text("# synthetic runtime\n")
    for name in ("LICENSE", "NOTICE"):
        (remote / name).write_text("Synthetic public legal file\n")
    (remote / "laya.gif").write_bytes(os.urandom(2_000_000))
    git(remote, "add", ".")
    git(remote, "commit", "-m", "Synthetic source")
    return remote, git(remote, "rev-parse", "HEAD")


def test_sparse_partial_install_omits_unrelated_blob_and_reuses_pinned_commit(
    tmp_path,
):
    remote, revision = fixture_remote(tmp_path)
    root = tmp_path / "installation"
    script = laya_install.stage_laya(root)
    original = script.read_text()
    pin = original.split('revision="', 1)[1].split('"', 1)[0]
    script.write_text(
        original.replace(pin, revision).replace(
            "https://github.com/aayushch/laya.git", remote.as_uri()
        )
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    uv = binary / "uv"
    uv.write_text("#!/bin/sh\nexit 0\n")
    uv.chmod(0o700)
    environment = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
    }
    subprocess.run(
        ["sh", str(script)], env=environment, check=True, capture_output=True
    )
    upstream = root / "state/laya/upstream"
    assert (upstream / "engine/runtime.py").is_file()
    assert (upstream / "LICENSE").is_file()
    assert (upstream / "NOTICE").is_file()
    assert not (upstream / "laya.gif").exists()
    assert git(upstream, "config", "remote.origin.promisor") == "true"
    assert git(upstream, "config", "core.sparseCheckoutCone") == "false"
    gif_hash = git(remote, "rev-parse", "HEAD:laya.gif")
    missing = git(upstream, "rev-list", "--objects", "--missing=print", "HEAD")
    assert "?" + gif_hash in missing
    (upstream / "operator-note.txt").write_text("preserved")
    # No remote is available: a repeat must use its already-present pinned commit.
    git(upstream, "remote", "set-url", "origin", str(tmp_path / "unavailable"))
    subprocess.run(
        ["sh", str(script)], env=environment, check=True, capture_output=True
    )
    assert (upstream / "operator-note.txt").read_text() == "preserved"


def test_reviewed_previous_installer_upgrade_preserves_helpers_and_private_state(
    tmp_path,
):
    script = laya_install.stage_laya(tmp_path)
    expected = script.read_bytes()
    previous = PREVIOUS.read_bytes()
    assert (
        hashlib.sha256(previous).hexdigest()
        == laya_install.PREVIOUS_SETUP_SHA256
    )
    script.write_bytes(previous)
    private = tmp_path / "state/private"
    private.mkdir(parents=True)
    key = private / "operator-key"
    key.write_bytes(b"synthetic private state")
    helpers = {
        p: p.read_bytes() for p in script.parent.iterdir() if p != script
    }
    assert laya_install.stage_laya(tmp_path) == script
    assert script.read_bytes() == expected
    assert key.read_bytes() == b"synthetic private state"
    assert {p: p.read_bytes() for p in helpers} == helpers
    assert not list(script.parent.glob(".setup-upgrade-*"))


@pytest.mark.parametrize("change", [b"# operator changed installer\n", b"\n"])
def test_unreviewed_installer_never_upgrades(tmp_path, change):
    script = laya_install.stage_laya(tmp_path)
    modified = PREVIOUS.read_bytes() + change
    script.write_bytes(modified)
    with pytest.raises(ValueError, match="differ"):
        laya_install.stage_laya(tmp_path)
    assert script.read_bytes() == modified


def test_other_custom_helper_prevents_even_reviewed_installer_upgrade(tmp_path):
    script = laya_install.stage_laya(tmp_path)
    script.write_bytes(PREVIOUS.read_bytes())
    custom = script.parent / "semantic_worker.py"
    custom.write_text("custom worker")
    with pytest.raises(ValueError, match="differ"):
        laya_install.stage_laya(tmp_path)
    assert script.read_bytes() == PREVIOUS.read_bytes()
    assert custom.read_text() == "custom worker"
