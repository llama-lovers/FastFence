"""Expose a private FastMCP tool through FastFence's FastAPI and MCP interfaces."""

import json
import shutil
from pathlib import Path
from typing import Any

import uvicorn
from fastmcp import Client, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from fastfence.app.factory import create_app
from fastfence.app.interfaces.cli.initialize import initialize
from fastfence.modules.control.contracts.dto import Identity
from fastfence.shared.settings.app_settings import AppSettings

backend = FastMCP("Private text tools")


@backend.tool()
def uppercase(text: str) -> dict[str, str]:
    """An actual, deterministic operation; replace with your business logic."""
    return {"text": text.upper()}


class UppercaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=1024)


class ProtectedMCPTools:
    def supports(self, tool: str) -> bool:
        return tool == "text.uppercase"

    def validate(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]:
        if not self.supports(tool):
            raise ValueError("Unknown tool")
        return UppercaseInput.model_validate(arguments).model_dump()

    async def call(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]:
        # FastFence calls this only after authentication and input controls.
        if not self.supports(tool):
            raise ValueError("Unknown tool")
        async with Client(backend) as client:
            result = await client.call_tool("uppercase", arguments)
        if not isinstance(result.data, dict):
            raise ValueError("Unexpected MCP output")
        return result.data


def build_example(root: Path):
    """Use a separate config/state directory; never edit the operator's policy."""
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    for name in ("policy.yaml", "signatures.json"):
        target = config / name
        if not target.exists():
            shutil.copyfile(Path(__file__).with_name(name), target)
    initialize(root / "state")
    app = create_app(
        AppSettings(root=root, state=root / "state"), tools=ProtectedMCPTools()
    )

    @app.get("/integration-info")
    def integration_info():
        return {"tool": "text.uppercase", "mcp": "/mcp/", "rest": "/api/invoke"}

    return app


def main() -> None:
    root = Path("state/examples/fastmcp-integration").resolve()
    app = build_example(root)
    # Print paths only; keep provisioned bearer credentials private.
    print(json.dumps({"url": "http://127.0.0.1:8010", "state": str(root)}))
    uvicorn.run(app, host="127.0.0.1", port=8010)


if __name__ == "__main__":
    main()
