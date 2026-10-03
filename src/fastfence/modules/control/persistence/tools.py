"""Default tool transport: deny every unconnected business tool."""

from typing import Any

from fastfence.modules.control.domain.exceptions import ResourceDeniedError
from fastfence.modules.control.domain.models import Identity


class UnconfiguredTools:
    def supports(self, tool: str) -> bool:
        return False

    def validate(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]:
        raise ResourceDeniedError("tool_not_connected")

    async def call(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]:
        raise ResourceDeniedError("tool_not_connected")
