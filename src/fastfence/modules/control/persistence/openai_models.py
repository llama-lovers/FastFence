"""Bounded text-only transport to a trusted OpenAI-compatible model server."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import ModelMessage
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
            async with asyncio.timeout(timeout_ms / 1000):
                async with httpx.AsyncClient(
                    timeout=timeout_ms / 1000,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        self.url + "/chat/completions",
                        json=payload,
                        headers=headers,
                    ) as response:
                        response.raise_for_status()
                        if (
                            response.headers.get("content-encoding", "identity")
                            != "identity"
                        ):
                            raise ValueError(
                                "Encoded provider response refused"
                            )
                        body = bytearray()
                        async for chunk in response.aiter_bytes(
                            chunk_size=8192
                        ):
                            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise ValueError("Provider response too large")
                            body.extend(chunk)
                        return decode_completion(bytes(body), model, max_tokens)
        except Exception:
            raise ModelUnavailableError(
                "Model unavailable or invalid response"
            ) from None
