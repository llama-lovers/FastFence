"""Call a protected peer agent using the official Agent Communication SDK."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from acp_sdk.client import Client
from acp_sdk.models import Message, MessagePart


async def run(args):
    token = os.environ.get("FASTFENCE_AGENT_TOKEN")
    if not token:
        values = json.loads(args.credentials.read_text())
        token = values.get("local-agent") or values["analyst-blue"]
    async with Client(
        base_url=args.url.rstrip("/") + "/acp",
        headers={"Authorization": "Bearer " + token},
        timeout=120,
        trust_env=False,
    ) as client:
        agents = [agent.name async for agent in client.agents()]
        print(json.dumps({"available_agents": agents}))
        result = await client.run_sync(
            agent=args.agent,
            input=[
                Message(role="user", parts=[MessagePart(content=args.prompt)])
            ],
        )
        print(result.model_dump_json(indent=2))
        return result.status.value == "completed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8030")
    parser.add_argument("--agent", default="uppercase")
    parser.add_argument("--prompt", default="hello")
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path("state/examples/acp-gateway/state/credentials.json"),
    )
    if not asyncio.run(run(parser.parse_args())):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
