"""Bounded text-only transport to a trusted OpenAI-compatible model server."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt

from fastfence.modules.control.domain.exceptions import (
    ModelCapacityExceededError,
    ModelUnavailableError,
)
from fastfence.modules.control.domain.models import ModelMessage
from fastfence.modules.control.persistence.model_http import ModelHTTP
from fastfence.shared.settings.upstream_url import validate_openai_base_url

MAX_RESPONSE_BYTES = 262_144


class ProviderRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class Message(ProviderRecord):
    role: Literal["assistant"]
    content: str = Field(max_length=65_536)
    tool_calls: list[Any] | None = None
    function_call: dict[str, Any] | None = None
    refusal: str | None = None


class Choice(ProviderRecord):
    index: StrictInt = Field(ge=0, le=0)
    message: Message
    finish_reason: Literal["stop", "length"]


class Usage(ProviderRecord):
    prompt_tokens: StrictInt = Field(ge=0)
    completion_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)


class Completion(ProviderRecord):
    choices: list[Choice] = Field(min_length=1, max_length=1)
    usage: Usage


def unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate provider field")
        result[key] = value
    return result


def decode_completion(
    content: bytes, model: str, max_tokens: int
) -> tuple[dict[str, Any], int]:
    result = Completion.model_validate(
        json.loads(content, object_pairs_hook=unique_fields)
    )
    choice, usage = result.choices[0], result.usage
    if (
        choice.message.tool_calls
        or choice.message.function_call is not None
        or choice.message.refusal is not None
        or len(choice.message.content.encode()) > 65_536
        or usage.completion_tokens > max_tokens
        or usage.total_tokens != usage.prompt_tokens + usage.completion_tokens
    ):
        raise ValueError("Invalid provider completion")
    return {
        "text": choice.message.content,
        "model": model,
        "finish_reason": choice.finish_reason,
    }, usage.total_tokens


class OpenAIModels:
    def __init__(self, url: str, api_key: SecretStr | None = None) -> None:
        self.url = validate_openai_base_url(url)
        self._api_key = api_key
        self._http = ModelHTTP()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(
        self,
        model: str,
        prompt: str,
        max_tokens: int,
        timeout_ms: int,
        stop: list[str] | None = None,
        messages: list[ModelMessage] | None = None,
    ) -> tuple[dict[str, Any], int]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [message.model_dump() for message in messages]
            if messages is not None
            else [{"role": "user", "content": prompt}],
            "stream": False,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if stop is not None:
            payload["stop"] = stop
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if self._api_key is not None:
            headers["Authorization"] = (
                "Bearer " + self._api_key.get_secret_value()
            )
        try:
            response = await self._http.post(
                self.url + "/chat/completions",
                json=payload,
                headers=headers,
                timeout_ms=timeout_ms,
                max_response_bytes=MAX_RESPONSE_BYTES,
            )
            return decode_completion(response.content, model, max_tokens)
        except ModelCapacityExceededError:
            raise
        except Exception:
            raise ModelUnavailableError(
                "Model unavailable or invalid response"
            ) from None
