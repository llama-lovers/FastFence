"""Separate example gateway: real ACP forwarding through installed FastFence."""

import argparse
import shutil
from pathlib import Path

import uvicorn

from fastfence.app.factory import create_app
from fastfence.app.interfaces.cli.initialize import initialize
from fastfence.shared.acp import ACPAgentSettings
from fastfence.shared.settings.app_settings import AppSettings


def build_example(upstream_url: str = "http://127.0.0.1:8020"):
    token_file = Path("state/examples/acp-upstream-token.txt")
    if not token_file.is_file():
        raise SystemExit("Start the ACP example server first")
    root = Path("state/examples/acp-gateway").resolve()
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    for source, target in (
        ("acp_policy.yaml", "policy.yaml"),
        ("signatures.json", "signatures.json"),
    ):
        destination = config / target
        if not destination.exists():
            shutil.copyfile(Path(__file__).with_name(source), destination)
    initialize(root / "state")
    return create_app(
        AppSettings(
            root=root,
            state=root / "state",
            acp_agents={
                "uppercase": ACPAgentSettings(
                    base_url=upstream_url,
                    agent_name="uppercase",
                    api_key=token_file.read_text().strip(),
                )
            },
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8030)
    parser.add_argument("--upstream-url", default="http://127.0.0.1:8020")
    args = parser.parse_args()
    uvicorn.run(
        build_example(args.upstream_url), host="127.0.0.1", port=args.port
    )
