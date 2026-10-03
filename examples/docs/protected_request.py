"""Call your protected Qwen model through the actual FastFence REST API."""

import argparse
import json
import os
from pathlib import Path

import httpx


def agent_token(path: Path) -> str:
    if value := os.environ.get("FASTFENCE_AGENT_TOKEN"):
        return value
    if path == Path("state/credentials.json") and not path.exists():
        path = Path("state/demo-tokens.json")
    values = json.loads(path.read_text())
    return values.get("local-agent") or values["analyst-blue"]


def complete(client: httpx.Client, token: str, model: str, prompt: str) -> dict:
    response = client.post(
        "/api/models/complete",
        headers={"Authorization": "Bearer " + token},
        json={"model": model, "prompt": prompt, "max_output_tokens": 256},
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--credentials", type=Path, default=Path("state/credentials.json")
    )
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--prompt", default="Hello")
    args = parser.parse_args()
    with httpx.Client(
        base_url=args.url, timeout=120, trust_env=False
    ) as client:
        result = complete(
            client, agent_token(args.credentials), args.model, args.prompt
        )
    # HTTP 200 can carry a blocked verdict: always inspect these fields.
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "decision",
                    "reason",
                    "request_id",
                    "policy_version",
                    "semantic_provider",
                    "semantic_input_status",
                    "semantic_output_status",
                    "upstream_executed",
                    "output",
                )
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
