"""Wheel OCR setup uses reviewed hashes and its own interpreter."""

from importlib.resources import files
from unittest.mock import Mock

import pytest

from fastfence.app.interfaces.cli import ocr_install


def test_packaged_ocr_lock_has_required_pins_and_hashes():
    content = (
        files("fastfence.shared.defaults")
        .joinpath("ocr-requirements.txt")
        .read_text()
    )
    for requirement in (
        "paddleocr==3.4.0",
        "paddlepaddle==3.3.0",
        "pypdfium2==5.13.0",
        "pillow==12.3.0",
    ):
        assert requirement in content
    assert "--hash=sha256:" in content
    assert "-e ." not in content and "file://" not in content


def test_setup_installs_isolated_hashed_dependencies_then_models(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(ocr_install.shutil, "which", lambda _: "/fixture/uv")
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(ocr_install.subprocess, "run", run)
    state = tmp_path / "state"
    ocr_install.setup_ocr(state)
    commands = [call.args[0] for call in run.call_args_list]
    assert commands[0][:4] == ["uv", "venv", "--python", "3.12"]
    assert "--require-hashes" in commands[1]
    assert commands[1][commands[1].index("--python") + 1] == str(
        state / "private/ocr-env/bin/python"
    )
    assert commands[2][1:3] == [
        "-m",
        "fastfence.modules.ocr.persistence.bootstrap",
    ]
    assert commands[2][-1] == str(state / "private/ocr-models")
    assert run.call_args.kwargs["env"]["PYTHONPATH"]


def test_missing_uv_does_not_create_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_install.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit, match="pip install uv"):
        ocr_install.setup_ocr(tmp_path / "state")
    assert not (tmp_path / "state").exists()


def test_dependency_failure_does_not_bootstrap_models(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_install.shutil, "which", lambda _: "/fixture/uv")
    run = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr(ocr_install.subprocess, "run", run)
    with pytest.raises(SystemExit, match="OCR setup failed"):
        ocr_install.setup_ocr(tmp_path)
    assert run.call_count == 1
