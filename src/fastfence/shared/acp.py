"""Bounded stateless text-only Agent Communication Protocol contracts."""

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    ConfigDict,
    Field,
    SecretStr,
    StrictInt,
    field_validator,
    model_validator,
)

from fastfence.shared.models import StrictModel
from fastfence.shared.settings.upstream_url import validate_openai_base_url

ACPName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$",
    ),
]
ACPRole = Annotated[
    str, Field(max_length=80, pattern=r"^(user|agent(?:/[a-zA-Z0-9_-]+)?)$")
]


class ACPTextPart(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: str = Field(min_length=1, max_length=16_384)
    content_type: Literal["text/plain"] = "text/plain"
    content_encoding: Literal["plain"] = "plain"
    content_url: None = None
    name: None = None
    metadata: None = None


class ACPMessage(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: ACPRole
    parts: list[ACPTextPart] = Field(min_length=1, max_length=32)
    created_at: datetime | None = Field(default=None, exclude=True)
    completed_at: datetime | None = Field(default=None, exclude=True)

    @field_validator("created_at", "completed_at", mode="before")
    @classmethod
    def timestamp(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError("Invalid ACP timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("ACP timestamps require a timezone")
        return parsed


class ACPInput(StrictModel):
    input: list[ACPMessage] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def bounded_text(self) -> Self:
        if (
            sum(
                len(part.content.encode())
                for msg in self.input
                for part in msg.parts
            )
            > 65_536
        ):
            raise ValueError("ACP text input exceeds its byte limit")
        return self


class ACPContentMessage(StrictModel):
    role: StrictInt = Field(ge=0, le=1)
    parts: list[Annotated[str, Field(min_length=1, max_length=16_384)]] = Field(
        min_length=1, max_length=32
    )


class ACPToolInput(StrictModel):
    input: list[ACPContentMessage] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def bounded_text(self) -> Self:
        if (
            sum(len(part.encode()) for msg in self.input for part in msg.parts)
            > 65_536
        ):
            raise ValueError("ACP text input exceeds its byte limit")
        return self


def project_messages(messages: list[ACPMessage]) -> list[dict[str, Any]]:
    return [
        {
            "role": 0 if message.role == "user" else 1,
            "parts": [part.content for part in message.parts],
        }
        for message in messages
    ]


def restore_messages(messages: list[Any]) -> list[dict[str, Any]]:
    validated = ACPToolInput.model_validate({"input": messages})
    return [
        {
            "role": "user" if message.role == 0 else "agent",
            "parts": [
                {
                    "content": part,
                    "content_type": "text/plain",
                    "content_encoding": "plain",
                }
                for part in message.parts
            ],
        }
        for message in validated.input
    ]


class ACPAgentSettings(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    agent_name: ACPName
    api_key: SecretStr | None = Field(default=None, repr=False)
    timeout_seconds: float = Field(default=30, ge=0.1, le=60)

    @field_validator("base_url")
    @classmethod
    def trusted_origin(cls, value: str) -> str:
        try:
            return validate_openai_base_url(value)
        except ValueError:
            raise ValueError(
                "ACP base URL requires HTTPS or loopback HTTP without credentials, query or fragment"
            ) from None
