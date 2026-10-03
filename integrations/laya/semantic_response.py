"""Validate actual provider completion before LiteLLM or Laya can normalize it."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any


def unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate classifier field")
        result[key] = value
    return result


def validate_provider_response(response: Any) -> None:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("Invalid classifier choices")
    choice = choices[0]
    if getattr(choice, "finish_reason", None) != "stop":
        raise ValueError("Classifier completion did not explicitly stop")
    message = getattr(choice, "message", None)
    if (
        getattr(response, "truncated", False)
        or getattr(choice, "truncated", False)
        or getattr(message, "tool_calls", None)
        or getattr(message, "function_call", None)
        or getattr(message, "refusal", None)
    ):
        raise ValueError("Invalid classifier completion mode")
    content = getattr(message, "content", None)
    if not isinstance(content, str) or len(content.encode()) > 1024:
        raise ValueError("Invalid classifier content")
    answer = json.loads(content, object_pairs_hook=unique_fields)
    if (
        not isinstance(answer, dict)
        or set(answer) != {"severity"}
        or answer["severity"] not in ("benign", "suspicious", "malicious")
    ):
        raise ValueError("Invalid classifier severity")


def guard_provider_completion(
    original: Callable[..., Awaitable[tuple[dict, Any]]],
) -> Callable[..., Awaitable[tuple[dict, Any]]]:
    async def guarded(*args: Any, **kwargs: Any) -> tuple[dict, Any]:
        result = await original(*args, **kwargs)
        validate_provider_response(result[1])
        return result

    return guarded


def install_provider_validation() -> None:
    from litellm.llms.openai.openai import OpenAIChatCompletion

    # This pinned seam returns the original OpenAI SDK completion before
    # LiteLLM Choices and Laya both default missing finish_reason to "stop".
    OpenAIChatCompletion.make_openai_chat_completion_request = (
        guard_provider_completion(
            OpenAIChatCompletion.make_openai_chat_completion_request
        )
    )
