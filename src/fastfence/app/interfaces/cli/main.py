from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from fastfence.app.interfaces.cli.bootstrap_config import initialize_config
from fastfence.app.interfaces.cli.bootstrap_ocr import ensure_ocr
from fastfence.app.interfaces.cli.bootstrap_runtime import initialize_runtime
from fastfence.app.interfaces.cli.initialize import (
    initialize,
    initialize_anonymization,
)
from fastfence.app.interfaces.cli.laya_install import setup_laya
from fastfence.app.interfaces.cli.ocr_install import setup_ocr
from fastfence.app.interfaces.cli.startup import (
    doctor,
    preflight,
    startup_error,
)
from fastfence.shared.settings.app_settings import AppSettings


def _initialize(settings: AppSettings, config_only: bool) -> None:
    initialize_config(
        settings.root, max_source_bytes=settings.max_config_source_bytes
    )
    external_identity = (
        settings.identity_config_json is not None
        or settings.identity_config_file is not None
    )
    if not external_identity:
        initialize(settings.state_path)
    initialize_anonymization(settings)
    if external_identity:
        preflight(settings)
        print(
            "Configured external identities validated; local credentials were not created."
        )
    if config_only:
        print(
            "Configuration initialized; runtime components were not installed (--config-only)."
        )
    else:
        initialize_runtime(settings)


def _serve(settings: AppSettings, host: str, port: int) -> None:
    preflight(settings)
    print(f"FastFence dashboard: http://{host}:{port}", flush=True)
    uvicorn.run(
        "fastfence.app.factory:create_app", factory=True, host=host, port=port
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="FastFence AI Control Layer")
    parser.add_argument(
        "command",
        nargs="?",
        help="Omit to prepare required components and start the dashboard; commands provide advanced control.",
        choices=["init", "serve", "doctor", "setup-laya", "setup-ocr"],
    )
    parser.add_argument(
        "--state", help="Private state directory (overrides .env)"
    )
    parser.add_argument(
        "--anonymization",
        action="store_true",
        help="Compatibility flag: init always preserves or provisions the private keyring",
    )
    parser.add_argument(
        "--config-only",
        action="store_true",
        help="Init: create local configuration and keys without network or model installation",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Doctor: require Laya, OCR, Qwen and anonymization readiness",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.config_only and args.command != "init":
        parser.error("--config-only requires the explicit init command")
    previous_state = os.environ.get("FASTFENCE_STATE")
    if args.state is not None:
        os.environ["FASTFENCE_STATE"] = str(Path(args.state).resolve())
    try:
        settings = AppSettings.environment()
        if args.command is None:
            _initialize(settings, config_only=False)
            _serve(ensure_ocr(settings), args.host, args.port)
        elif args.command == "init":
            _initialize(settings, config_only=args.config_only)
        elif args.command == "setup-laya":
            setup_laya(settings.authoring_root or settings.root)
        elif args.command == "setup-ocr":
            setup_ocr(settings.state_path)
        elif args.command == "doctor":
            doctor(settings, full=args.full)
        else:
            _serve(settings, args.host, args.port)
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit(startup_error()) from None
    finally:
        if previous_state is None:
            os.environ.pop("FASTFENCE_STATE", None)
        else:
            os.environ["FASTFENCE_STATE"] = previous_state


if __name__ == "__main__":
    main()
