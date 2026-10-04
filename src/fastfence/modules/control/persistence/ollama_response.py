"""Strict non-streaming native Ollama text completion contracts."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class CompletionMetadata(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    done: StrictBool
    done_reason: Literal["stop", "length"]
    prompt_eval_count: int = Field(ge=0)
    eval_count: int = Field(ge=0)
    error: None = None

    @field_validator("done")
    @classmethod
    def require_completed(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Incomplete provider response")
        return value


class ChatMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    role: Literal["assistant"]
    content: str
    tool_calls: list[Any] | None = Field(default=None, max_length=0)
    images: list[Any] | None = Field(default=None, max_length=0)


class ChatCompletion(CompletionMetadata):
    message: ChatMessage


class GenerateCompletion(CompletionMetadata):
    response: str


def decode_completion(
    data: Any, *, chat: bool, max_tokens: int
) -> tuple[str, str, int]:
    if chat:
        completion = ChatCompletion.model_validate(data)
        text = completion.message.content
    else:
        completion = GenerateCompletion.model_validate(data)
        text = completion.response
    if completion.eval_count > max_tokens:
        raise ValueError("Provider violated token limit")
    return (
        text,
        completion.done_reason,
        completion.prompt_eval_count + completion.eval_count,
    )
