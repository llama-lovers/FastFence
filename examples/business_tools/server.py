"""Opt-in example application with simulated business handlers on port 8001."""

import shutil
from pathlib import Path

import uvicorn

from examples.business_tools.credentials import initialize
from examples.business_tools.tools import DemoTools
from fastfence.app.factory import create_app
from fastfence.shared.settings.app_settings import AppSettings


def main() -> None:
    root = Path("state/examples/business-tools").resolve()
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    for source, destination in [
        (Path(__file__).with_name("policy.yaml"), config / "policy.yaml"),
        (Path("config/signatures.json"), config / "signatures.json"),
    ]:
        if not destination.exists():
            shutil.copyfile(source, destination)
    initialize(root)
    app = create_app(AppSettings(root=root, state=root), tools=DemoTools())
    uvicorn.run(app, host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
