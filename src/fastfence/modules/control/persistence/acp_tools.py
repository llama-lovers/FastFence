"""Trusted synchronous ACP text calls through the existing tool policy pipeline."""

import asyncio
import json
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from fastfence.modules.control.domain.exceptions import ResourceDeniedError
from fastfence.modules.control.domain.models import Identity
from fastfence.shared.acp import (
    ACPAgentSettings,
    ACPInput,
    ACPRole,
    ACPToolInput,
    project_messages,
    restore_messages,
)

MAX_RESPONSE_BYTES = 262_144


class ProviderPart(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    content: str = Field(min_length=1, max_length=16_384)
    content_type: Literal["text/plain"] = "text/plain"
    content_encoding: Literal["plain"] = "plain"
    content_url: None = None


class ProviderMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    role: ACPRole
    parts: list[ProviderPart] = Field(min_length=1, max_length=32)


class ProviderRun(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    agent_name: str
    status: Literal["completed"]
    output: list[ProviderMessage] = Field(min_length=1, max_length=32)
    session_id: UUID | None = Field(default=None, exclude=True)
    session: None = None
    await_request: None = None
    error: None = None

    @field_validator("session_id", mode="before")
    @classmethod
    def discarded_session_identifier(cls, value: Any) -> UUID | None:
        # Official SDK creates a fresh session even when none was requested.
        # Validate its opaque identifier, then discard it without ever reusing it.
        if value is None:
            return None
        if not isinstance(value, str) or len(value) != 36:
            raise ValueError("Invalid ACP session identifier")
        return UUID(value)


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate ACP response field")
        result[name] = value
    return result


def decode_run(body: bytes, agent_name: str) -> dict[str, Any]:
    result = ProviderRun.model_validate(
        json.loads(body, object_pairs_hook=_unique_fields)
    )
    if result.agent_name != agent_name:
        raise ValueError("Unexpected ACP response agent")
    normalized = ACPInput.model_validate(
        {
            "input": [
                message.model_dump(exclude_none=True)
                for message in result.output
            ]
        }
    )
    return {"output": project_messages(normalized.input)}


class ACPTools:
    def __init__(self, agents: dict[str, ACPAgentSettings]) -> None:
        self._agents = {
            "acp." + alias: config for alias, config in agents.items()
        }

    def supports(self, tool: str) -> bool:
        return tool in self._agents

    def validate(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]:
        if not self.supports(tool):
            raise ResourceDeniedError("tool_not_connected")
        return ACPToolInput.model_validate(arguments).model_dump()

    async def call(
        self, tool: str, arguments: dict[str, Any], identity: Identity
    ) -> dict[str, Any]:
        payload = self.validate(tool, arguments, identity)
        config = self._agents[tool]
        payload["input"] = restore_messages(payload["input"])
        payload.update(agent_name=config.agent_name, mode="sync")
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if config.api_key is not None:
            headers["Authorization"] = (
                "Bearer " + config.api_key.get_secret_value()
            )
        try:
            async with asyncio.timeout(config.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=config.timeout_seconds,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        config.base_url + "/runs",
                        json=payload,
                        headers=headers,
                    ) as response:
                        if (
                            response.status_code != 200
                            or response.headers.get(
                                "content-encoding", "identity"
                            )
                            != "identity"
                        ):
                            raise ValueError("Unsupported ACP response")
                        body = bytearray()
                        async for chunk in response.aiter_bytes(
                            chunk_size=8192
                        ):
                            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise ValueError(
                                    "ACP response exceeds byte limit"
                                )
                            body.extend(chunk)
                        return decode_run(bytes(body), config.agent_name)
        except TimeoutError:
            raise TimeoutError("ACP agent timeout") from None
        except Exception:
            raise RuntimeError(
                "ACP agent unavailable or invalid response"
            ) from None
