"""Wheel helper installation preserves local files and the reviewed pin."""

from unittest.mock import Mock

import pytest

from fastfence.app.interfaces.cli import laya_install


def test_stage_helpers_is_complete_and_repeatable(tmp_path):
    script = laya_install.stage_laya(tmp_path)
    assert script == tmp_path / "integrations/laya/setup.sh"
    assert {p.name for p in script.parent.iterdir()} == set(
        laya_install.LAYA_FILES
    )
    assert b"b3b998c03dc44076675305581eb4640b9bf6ff8f" in script.read_bytes()  # pragma: allowlist secret - public upstream commit
    before = {p.name: p.read_bytes() for p in script.parent.iterdir()}
    laya_install.stage_laya(tmp_path)
    assert before == {p.name: p.read_bytes() for p in script.parent.iterdir()}


def test_existing_custom_helper_is_not_overwritten(tmp_path):
    destination = tmp_path / "integrations/laya"
    destination.mkdir(parents=True)
    path = destination / "semantic_worker.py"
    path.write_text("custom helper")
    with pytest.raises(ValueError, match="differ"):
        laya_install.stage_laya(tmp_path)
    assert path.read_text() == "custom helper"
    assert list(destination.iterdir()) == [path]


def test_missing_prerequisite_is_actionable_and_does_not_write(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(laya_install.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit, match="pip install uv"):
        laya_install.setup_laya(tmp_path)
    assert not (tmp_path / "integrations").exists()


def test_setup_executes_only_staged_pinned_installer(tmp_path, monkeypatch):
    monkeypatch.setattr(
        laya_install.shutil, "which", lambda _: "/fixture/bin/tool"
    )
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(laya_install.subprocess, "run", run)
    laya_install.setup_laya(tmp_path)
    run.assert_called_once_with(
        ["sh", str(tmp_path / "integrations/laya/setup.sh")],
        cwd=tmp_path,
        check=False,
    )


def test_installer_failure_never_reports_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        laya_install.shutil, "which", lambda _: "/fixture/bin/tool"
    )
    monkeypatch.setattr(
        laya_install.subprocess, "run", Mock(return_value=Mock(returncode=1))
    )
    with pytest.raises(SystemExit, match="setup failed"):
        laya_install.setup_laya(tmp_path)
    assert "Laya installed" not in capsys.readouterr().out
