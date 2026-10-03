from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import ValidationError

from fastfence.core.engine import Engine
from fastfence.core.identity import IdentityStore
from fastfence.core.schema import ToolCall


class ProvisionedTokenVerifier(TokenVerifier):
    def __init__(self, identities: IdentityStore):
        super().__init__()
        self.identities = identities

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self.identities.authenticate(token)
        if identity is None or identity.admin:
            return None
        return AccessToken(
            token=token, client_id=identity.subject, subject=identity.subject, scopes=["invoke"]
        )


def create_mcp(engine: Engine, identities: IdentityStore):
    mcp = FastMCP(
        "FastFence controlled tools",
        auth=ProvisionedTokenVerifier(identities),
        mask_error_details=True,
    )

    def identity():
        token = get_access_token()
        actor = identities.by_subject(token.subject) if token else None
        if actor is None or actor.admin:
            raise ToolError("Verified agent credential required")
        return actor

    @mcp.tool()
    async def invoke(tool: str, arguments: dict) -> dict:
        """Invoke an allowlisted business tool through FastFence's complete policy pipeline."""
        try:
            call = ToolCall(tool=tool, arguments=arguments)
        except ValidationError:
            raise ToolError("Invalid invocation schema") from None
        verdict = await engine.invoke(identity(), call)
        return verdict.model_dump()

    @mcp.resource("memory://{tenant}/{key}")
    async def memory(tenant: str, key: str) -> dict:
        """Read a tenant-scoped memory resource through identical policy and output controls."""
        verdict = await engine.invoke(
            identity(), ToolCall(tool="memory.read", arguments={"resource": f"{tenant}/{key}"})
        )
        if verdict.decision in {"blocked", "error"}:
            raise ToolError(f"{verdict.reason}; request_id={verdict.request_id}")
        return verdict.model_dump()

    return mcp
