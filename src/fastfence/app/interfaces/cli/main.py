from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from fastfence.app.interfaces.cli.bootstrap_config import initialize_config
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


def main() -> None:
    parser = argparse.ArgumentParser(description="FastFence AI Control Layer")
    parser.add_argument(
        "command",
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
    previous_state = os.environ.get("FASTFENCE_STATE")
    if args.state is not None:
        os.environ["FASTFENCE_STATE"] = str(Path(args.state).resolve())
    try:
        settings = AppSettings.environment()
        if args.command == "init":
            initialize_config(
                settings.root, max_source_bytes=settings.max_config_source_bytes
            )
            initialize(settings.state_path)
            initialize_anonymization(settings)
            if args.config_only:
                print(
                    "Configuration initialized; runtime components were not installed (--config-only)."
                )
            else:
                initialize_runtime(settings)
        elif args.command == "setup-laya":
            setup_laya(settings.authoring_root or settings.root)
        elif args.command == "setup-ocr":
            setup_ocr(settings.state_path)
        elif args.command == "doctor":
            doctor(settings, full=args.full)
        else:
            preflight(settings)
            uvicorn.run(
                "fastfence.app.factory:create_app",
                factory=True,
                host=args.host,
                port=args.port,
            )
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit(startup_error()) from None
    finally:
        if previous_state is None:
            os.environ.pop("FASTFENCE_STATE", None)
        else:
            os.environ["FASTFENCE_STATE"] = previous_state


if __name__ == "__main__":
    main()
