"""Read-only readiness checks. Diagnostic output excludes private input values."""

import os
import shlex
import subprocess
from pathlib import Path

import httpx

from fastfence.modules.control.application.facade import build_runtime
from fastfence.shared.settings.app_settings import AppSettings
from fastfence.workflows.anonymization import build_anonymization


def startup_error() -> str:
    return (
        "FastFence startup/configuration failed. No credentials were changed. "
        "Run `fastfence doctor` to check prerequisites. "
        "Check private identity/key configuration and config/policy.yaml; "
        "validation input is omitted to protect secrets."
    )


def preflight(settings: AppSettings) -> None:
    if settings.identity_config_json is None:
        path = (
            settings.identity_config_file
            or settings.state_path / "identities.json"
        )
        if not path.is_file():
            command = f"fastfence init --state {shlex.quote(str(settings.state_path))} --anonymization"
            hint = (
                "Provision FASTFENCE_IDENTITY_CONFIG_FILE at the configured location."
                if settings.identity_config_file
                else f"Initialize local credentials first: {command}"
            )
            raise SystemExit(
                f"FastFence cannot start: identity configuration is missing. {hint}"
            )
    for name in ("policy.yaml", "signatures.json"):
        if not (settings.root / "config" / name).is_file():
            raise SystemExit(
                f"FastFence cannot start: config/{name} is missing. Run from the repository root or set FASTFENCE_ROOT."
            )
    runtime = build_runtime(
        settings, anonymization=build_anonymization(settings)
    )
    try:
        snapshot = runtime.snapshot()
        if (
            snapshot.policy.anonymization.enabled
            and runtime.engine.anonymization is not None
        ):
            if settings.anonymization_keys_json is None:
                key_file = (
                    settings.anonymization_keys_file
                    or settings.state_path / "anonymization-keys.json"
                )
                if not key_file.is_file():
                    raise SystemExit(
                        "Anonymization is enabled but no keyring is configured. Run `fastfence init --anonymization` before serving."
                    )
    finally:
        runtime.close()


def _python_imports(interpreter: Path, modules: str) -> bool:
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        return False
    try:
        result = subprocess.run(
            [str(interpreter), "-B", "-c", modules],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _ocr_ready(settings: AppSettings) -> bool:
    if settings.ocr_python is None or settings.ocr_models is None:
        return False
    names = (
        "PP-LCNet_x1_0_doc_ori",
        "PP-OCRv5_mobile_det",
        "latin_PP-OCRv5_mobile_rec",
    )
    try:
        for name in names:
            for filename in (
                "inference.json",
                "inference.pdiparams",
                "inference.yml",
            ):
                path = settings.ocr_models / name / filename
                if not path.is_file() or path.stat().st_size == 0:
                    return False
    except OSError:
        return False
    return _python_imports(
        settings.ocr_python, "import paddle, paddleocr, pypdfium2, PIL"
    )


def _laya_ready(settings: AppSettings) -> bool:
    root = settings.authoring_root or settings.root
    paths = [
        root / "integrations/laya/draft_policy.py",
        root / "integrations/laya/semantic_worker.py",
        root / "state/laya/upstream/engine",
    ]
    return all(path.exists() for path in paths) and _python_imports(
        root / "state/laya/venv/bin/python",
        "import sys; "
        f"sys.path[:0] = {[str(root / 'integrations/laya'), str(root / 'state/laya/upstream/engine')]!r}; "
        "import semantic_worker, litellm; "
        "from laya.llm import client; assert callable(client.llm_call)",
    )


def _ollama_ready(settings: AppSettings) -> bool:
    try:
        runtime = build_runtime(
            settings, anonymization=build_anonymization(settings)
        )
        try:
            semantic = runtime.snapshot().policy.semantic
        finally:
            runtime.close()
        if semantic.provider not in {"laya", "ollama"}:
            return True
        with httpx.Client(timeout=3, trust_env=False) as client:
            response = client.get(settings.ollama_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            names = {item["name"] for item in response.json()["models"]}
        return semantic.model in names
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return False


def doctor(settings: AppSettings, *, full: bool = False) -> None:
    try:
        preflight(settings)
    except SystemExit as error:
        print(f"FAIL core: {error}")
        raise SystemExit(1) from None
    print(
        "OK core: identities, policy, signatures and configured keyring validated."
    )
    if not full:
        print(
            "Run `fastfence doctor --full` to check optional feature prerequisites."
        )
        return
    checks = [
        (
            "Laya authoring and text-assessment installation",
            _laya_ready(settings),
            "fastfence setup-laya",
        ),
        (
            "OCR interpreter and model files",
            _ocr_ready(settings),
            "fastfence setup-ocr",
        ),
        (
            "Configured semantic assessor availability",
            _ollama_ready(settings),
            "ollama serve; fastfence init",
        ),
        (
            "anonymization keyring",
            settings.anonymization_keys_json is not None
            or (
                settings.anonymization_keys_file
                or settings.state_path / "anonymization-keys.json"
            ).is_file(),
            "fastfence init --anonymization",
        ),
    ]
    for label, ready, fix in checks:
        print(
            f"{'OK' if ready else 'FAIL'} {label}"
            + ("" if ready else f": {fix}")
        )
    if not all(ready for _, ready, _ in checks):
        raise SystemExit(1)
    print(
        "Prerequisite checks passed. Run the manual scenarios to verify end-to-end model behavior."
    )
