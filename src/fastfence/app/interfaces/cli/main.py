from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from fastfence.app.interfaces.cli.bootstrap_config import initialize_config
from fastfence.app.interfaces.cli.initialize import (
    initialize,
    initialize_anonymization,
)
from fastfence.app.interfaces.cli.startup import (
    doctor,
    preflight,
    startup_error,
)
from fastfence.shared.settings.app_settings import AppSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="FastFence AI Control Layer")
    parser.add_argument("command", choices=["init", "serve", "doctor"])
    parser.add_argument(
        "--state", help="Private state directory (overrides .env)"
    )
    parser.add_argument(
        "--anonymization",
        action="store_true",
        help="Provision a private anonymization keyring during init",
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
            if args.anonymization:
                initialize_anonymization(settings)
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
