"""Use the actual FastMCP client for protected completion or a registered tool."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from fastmcp import Client
from fastmcp.client.auth import BearerAuth


def agent_token(path: Path) -> str:
    if value := os.environ.get("FASTFENCE_AGENT_TOKEN"):
        return value
    if path == Path("state/credentials.json") and not path.exists():
        path = Path("state/demo-tokens.json")
    values = json.loads(path.read_text())
    return values.get("local-agent") or values["analyst-blue"]


async def call_gateway(
    url: str,
    token: str,
    *,
    model: str = "qwen3:4b",
    prompt: str = "Hello",
    tool: str | None = None,
    arguments: dict | None = None,
) -> dict:
    async with Client(
        url.rstrip("/") + "/mcp/", auth=BearerAuth(token)
    ) as client:
        if tool is None:
            result = await client.call_tool(
                "complete",
                {"model": model, "prompt": prompt, "max_output_tokens": 256},
            )
        else:
            result = await client.call_tool(
                "invoke", {"tool": tool, "arguments": arguments or {}}
            )
        # FastMCP's structured result contains the full FastFence security verdict.
        return result.data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--credentials", type=Path, default=Path("state/credentials.json")
    )
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--prompt", default="Hello")
    parser.add_argument(
        "--tool",
        help="Requires an explicitly connected, allowlisted business adapter",
    )
    parser.add_argument(
        "--arguments", default="{}", help="JSON object for --tool"
    )
    args = parser.parse_args()
    arguments = json.loads(args.arguments)
    if not isinstance(arguments, dict):
        parser.error("--arguments must be a JSON object")
    result = asyncio.run(
        call_gateway(
            args.url,
            agent_token(args.credentials),
            model=args.model,
            prompt=args.prompt,
            tool=args.tool,
            arguments=arguments,
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
