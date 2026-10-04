from __future__ import annotations

import asyncio

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token, get_http_request
from pydantic import StrictBool, ValidationError

from fastfence.modules.control.contracts.dto import (
    Identity,
    ModelCall,
    ToolCall,
    Verdict,
)
from fastfence.modules.control.contracts.ports import (
    IdentityPort,
    InvocationPort,
)
from fastfence.modules.control.interfaces.mcp.cancellation import (
    until_disconnect,
)
from fastfence.shared.request_size import request_size


class ProvisionedTokenVerifier(TokenVerifier):
    def __init__(self, identities: IdentityPort) -> None:
        super().__init__()
        self.identities = identities

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self.identities.authenticate(token)
        if identity is None or identity.admin:
            return None
        return AccessToken(
            token=token,
            client_id=identity.subject,
            subject=identity.subject,
            scopes=["invoke"],
        )


async def protected(
    engine: InvocationPort, actor: Identity, call: ToolCall | ModelCall
) -> Verdict:
    try:
        scope = get_http_request().scope
    except RuntimeError:
        scope = {}
    event = scope.get("fastfence.disconnect_event")
    return await until_disconnect(
        lambda: engine.invoke(
            actor, call, preparation_bytes=request_size(scope)
        ),
        event if isinstance(event, asyncio.Event) else None,
    )


def create_mcp(engine: InvocationPort, identities: IdentityPort) -> FastMCP:
    mcp = FastMCP(
        "FastFence controlled tools",
        auth=ProvisionedTokenVerifier(identities),
        mask_error_details=True,
    )

    def identity() -> Identity:
        token = get_access_token()
        subject = token.subject if token else None
        actor = identities.by_subject(subject) if subject is not None else None
        if actor is None or actor.admin:
            raise ToolError("Verified agent credential required")
        return actor

    @mcp.tool()
    async def invoke(
        tool: str, arguments: dict, restore_originals: StrictBool = False
    ) -> dict[str, object]:
        """Invoke an allowlisted business tool through FastFence's complete policy pipeline."""
        try:
            call = ToolCall(
                tool=tool,
                arguments=arguments,
                restore_originals=restore_originals,
            )
        except ValidationError:
            raise ToolError("Invalid invocation schema") from None
        verdict = await protected(engine, identity(), call)
        return verdict.model_dump()

    @mcp.tool()
    async def complete(
        model: str,
        prompt: str,
        max_output_tokens: int = 256,
        restore_originals: StrictBool = False,
    ) -> dict[str, object]:
        """Call an allowlisted model through input/output controls, budgets and audit."""
        try:
            call = ModelCall(
                model=model,
                prompt=prompt,
                max_output_tokens=max_output_tokens,
                restore_originals=restore_originals,
            )
        except ValidationError:
            raise ToolError("Invalid completion schema") from None
        verdict = await protected(engine, identity(), call)
        return verdict.model_dump()

    @mcp.resource("memory://{tenant}/{key}")
    async def memory(tenant: str, key: str) -> dict[str, object]:
        """Read a tenant-scoped memory resource through identical policy and output controls."""
        verdict = await protected(
            engine,
            identity(),
            ToolCall(
                tool="memory.read", arguments={"resource": f"{tenant}/{key}"}
            ),
        )
        if verdict.decision in {"blocked", "error"}:
            raise ToolError(
                f"{verdict.reason}; request_id={verdict.request_id}"
            )
        return verdict.model_dump()

    return mcp
