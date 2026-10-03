"""Install hash-locked OCR dependencies for an installed wheel."""

import os
import shutil
import subprocess
from importlib.resources import as_file, files
from pathlib import Path


def _run(command: list[str], environment: dict[str, str]) -> None:
    if subprocess.run(command, env=environment, check=False).returncode:
        raise SystemExit(
            "OCR setup failed; resolve the installer error and retry."
        )


def setup_ocr(state: Path) -> None:
    if shutil.which("uv") is None:
        raise SystemExit(
            "OCR setup requires uv. Run `python -m pip install uv`, then retry `fastfence setup-ocr`."
        )
    private = state / "private"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    python = private / "ocr-env/bin/python"
    models = private / "ocr-models"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[4])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if not python.is_file():
        _run(
            ["uv", "venv", "--python", "3.12", str(python.parent.parent)],
            environment,
        )
    requirements = files("fastfence.shared.defaults").joinpath(
        "ocr-requirements.txt"
    )
    with as_file(requirements) as source:
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "-r",
                str(source),
            ],
            environment,
        )
    _run(
        [
            str(python),
            "-m",
            "fastfence.modules.ocr.persistence.bootstrap",
            str(models),
        ],
        environment,
    )
    print(
        "OCR dependencies and local mobile models installed. Restart FastFence to detect the configured state directory's OCR environment."
    )
