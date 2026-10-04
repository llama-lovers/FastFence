"""Actual ACP SDK text agent on loopback, protected by a separate private token."""

import argparse
import hmac
import os
import secrets
from pathlib import Path

import uvicorn
from acp_sdk.models import Message, MessagePart
from acp_sdk.server import Server
from acp_sdk.server.app import create_app
from fastapi import Request
from fastapi.responses import JSONResponse

TOKEN_FILE = Path("state/examples/acp-upstream-token.txt")
server = Server()


@server.agent(
    name="uppercase",
    input_content_types=["text/plain"],
    output_content_types=["text/plain"],
)
async def uppercase(input: list[Message]):
    """Uppercase actual incoming text; no model or simulated business result."""
    for message in input:
        yield Message(
            role="agent/uppercase",
            parts=[
                MessagePart(
                    content=part.content.upper(), content_type="text/plain"
                )
                for part in message.parts
            ],
        )


def private_token() -> str:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(
            TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError:
        return TOKEN_FILE.read_text().strip()
    with os.fdopen(descriptor, "w") as stream:
        stream.write(secrets.token_urlsafe(32) + "\n")
    return TOKEN_FILE.read_text().strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()
    token = private_token()
    if len(token) < 32:
        raise SystemExit("Invalid private ACP example credential")
    app = create_app(*server.agents, enable_playground_cors=False)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(
            supplied.encode(), ("Bearer " + token).encode()
        ):
            return JSONResponse(
                {"code": "invalid_input", "message": "Authentication required"},
                status_code=401,
            )
        return await call_next(request)

    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
