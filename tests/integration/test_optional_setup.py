"""Exercise setup orchestration without network downloads or heavyweight models."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("custom_state", [False, True])
def test_ocr_setup_isolated_locked_and_repeatable(
    tmp_path: Path, custom_state: bool
) -> None:
    checkout = tmp_path / "checkout with space $literal"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(ROOT / "scripts/setup-ocr.sh", scripts / "setup-ocr.sh")
    (checkout / ".env").write_text("UNRELATED_SETTING=keep\n")
    (checkout / ".venv").mkdir()
    sentinel = checkout / ".venv" / "sentinel"
    sentinel.write_text("gateway environment")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "root = pathlib.Path(os.environ['UV_PROJECT_ENVIRONMENT'])\n"
        "assert sys.argv[1:] == ['sync', '--locked', '--extra', 'ocr', '--no-default-groups']\n"
        "(root / 'bin').mkdir(parents=True, exist_ok=True)\n"
        "python = root / 'bin' / 'python'\n"
        f"python.write_text({f'#!{sys.executable}'!r} + '\\n' + "
        "'import os, pathlib, sys\\n' + "
        "\"if sys.argv[1:3] == ['-m', 'fastfence.modules.ocr.persistence.bootstrap']:\\n\" + "
        '"    pathlib.Path(sys.argv[3]).mkdir(parents=True, exist_ok=True)\\n" + '
        '"else:\\n    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\\n")\n'
        "python.chmod(0o700)\n"
    )
    uv.chmod(0o700)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }
    env.pop("FASTFENCE_STATE", None)
    state = checkout / "state"
    if custom_state:
        state = tmp_path / "custom state ' quoted"
        env["FASTFENCE_STATE"] = str(state)
    for _ in range(2):
        result = subprocess.run(
            ["sh", str(scripts / "setup-ocr.sh")],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "OCR installed from uv.lock" in result.stdout
    settings = state / "private/ocr.env"
    assert settings.stat().st_mode & 0o777 == 0o600
    # Load the actual generated file using a shell; expansions remain literal.
    loaded = subprocess.run(
        [
            "sh",
            "-c",
            'set -a; . "$1"; "$2" -c '
            '\'import json, os; print(json.dumps([os.environ["FASTFENCE_OCR_PYTHON"], os.environ["FASTFENCE_OCR_MODELS"]]))\'',
            "setup-test",
            str(settings),
            sys.executable,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(loaded.stdout) == [
        str(state / "private/ocr-env/bin/python"),
        str(state / "private/ocr-models"),
    ]
    assert (checkout / ".env").read_text() == "UNRELATED_SETTING=keep\n"
    assert sentinel.read_text() == "gateway environment"
