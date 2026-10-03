"""Prepare local OCR before the one-command dashboard starts."""

from fastfence.app.interfaces.cli.ocr_install import setup_ocr
from fastfence.app.interfaces.cli.startup import _ocr_ready
from fastfence.shared.settings.app_settings import AppSettings


def ensure_ocr(settings: AppSettings) -> AppSettings:
    if _ocr_ready(settings):
        print("OCR runtime is already installed.")
        return settings
    private = settings.state_path / "private"
    expected = {
        "ocr_python": private / "ocr-env/bin/python",
        "ocr_models": private / "ocr-models",
    }
    for name, default in expected.items():
        configured = getattr(settings, name)
        if (
            configured is not None
            and configured.absolute() != default.absolute()
        ):
            raise SystemExit(
                "Configured OCR runtime is unavailable. Check FASTFENCE_OCR_PYTHON and "
                "FASTFENCE_OCR_MODELS, then retry `uv tool run fastfence`. "
                "Custom runtime paths were preserved."
            )
    print(
        "Preparing OCR dependencies and local models; this may take several minutes.",
        flush=True,
    )
    setup_ocr(settings.state_path)
    refreshed = AppSettings.environment()
    if not _ocr_ready(refreshed):
        raise SystemExit(
            "OCR setup did not produce a usable runtime. Resolve the installation "
            "error and retry `uv tool run fastfence`; existing private state was preserved."
        )
    return refreshed
