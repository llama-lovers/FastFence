"""A deliberately bounded OpenAI compatibility surface for protected Laya calls."""

from __future__ import annotations

import time
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field, ValidationError, field_validator

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.contracts.dto import (
    Identity,
    ModelCall,
    ModelMessage,
    Verdict,
)
from fastfence.shared.models import StrictModel

MAX_BODY_BYTES = 65_536


class ChatMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=65_536)


class ChatCompletionRequest(StrictModel):
    model: str = Field(min_length=1, max_length=100)
    messages: list[ChatMessage] = Field(min_length=1, max_length=32)
    max_tokens: int = Field(default=256, ge=1, le=65_536, strict=True)
    stream: Literal[False] = False
    temperature: float = Field(default=0.0, ge=0, le=0, strict=True)
    n: Literal[1] = 1
    stop: (
        Annotated[str, Field(min_length=1, max_length=128)]
        | Annotated[
            list[Annotated[str, Field(min_length=1, max_length=128)]],
            Field(min_length=1, max_length=4),
        ]
        | None
    ) = None

    @field_validator("messages")
    @classmethod
    def require_user_message(
        cls, value: list[ChatMessage]
    ) -> list[ChatMessage]:
        if not any(message.role == "user" for message in value):
            raise ValueError("At least one user message is required")
        return value

    def as_model_call(self, *, restore_originals: bool = False) -> ModelCall:
        stop = [self.stop] if isinstance(self.stop, str) else self.stop
        return ModelCall(
            model=self.model,
            prompt="",
            messages=[
                ModelMessage(role=message.role, content=message.content)
                for message in self.messages
            ],
            max_output_tokens=min(self.max_tokens, 2048),
            stop=stop,
            restore_originals=restore_originals,
        )


def error_response(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": "FastFence rejected this request.",
                "type": "invalid_request_error",
                "code": code,
            }
        },
    )


def authenticated(runtime: ControlRuntime, request: Request) -> Identity | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    return runtime.authenticate(authorization.removeprefix("Bearer "))


async def read_payload(
    request: Request,
) -> ChatCompletionRequest | JSONResponse:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            return error_response(413, "body_too_large")
        body.extend(chunk)
    try:
        return ChatCompletionRequest.model_validate_json(body)
    except ValidationError:
        return error_response(422, "unsupported_or_invalid_request")


def verdict_response(verdict: Verdict, model: str) -> JSONResponse:
    metadata = {
        "request_id": verdict.request_id,
        "policy_version": verdict.policy_version,
        "feed_version": verdict.feed_version,
        "decision": verdict.decision,
        "upstream_executed": verdict.upstream_executed,
        "budget_units": verdict.tokens,
        "anonymized": verdict.anonymized,
        "restored": verdict.restored,
    }
    headers = {
        "X-FastFence-Request-Id": verdict.request_id,
        "X-FastFence-Policy-Version": str(verdict.policy_version),
        "X-FastFence-Feed-Version": str(verdict.feed_version),
        "X-FastFence-Decision": verdict.decision,
        "X-FastFence-Upstream-Executed": str(verdict.upstream_executed).lower(),
    }
    if verdict.decision not in {"allowed", "redacted"}:
        return JSONResponse(
            status_code=403 if verdict.decision == "blocked" else 503,
            headers=headers,
            content={
                "error": {
                    "message": "FastFence denied or could not complete this request.",
                    "type": "permission_denied",
                    "code": verdict.reason,
                },
                "fastfence": metadata,
            },
        )
    output = verdict.output
    if not isinstance(output, dict) or not isinstance(output.get("text"), str):
        return error_response(503, "invalid_protected_output")
    finish_reason = output.get("finish_reason", "stop")
    if finish_reason not in ("stop", "length"):
        return error_response(503, "invalid_protected_output")
    return JSONResponse(
        headers=headers,
        content={
            "id": f"chatcmpl-{verdict.request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": output["text"]},
                    "finish_reason": finish_reason,
                }
            ],
            # Budget units include safety scans and are not provider billing usage.
            "usage": None,
            "fastfence": metadata,
        },
    )


def create_router(runtime: ControlRuntime) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["Protected OpenAI compatibility"])

    @router.get("/models")
    async def models(request: Request) -> JSONResponse:
        identity = authenticated(runtime, request)
        if identity is None:
            return error_response(401, "authentication_required")
        if identity.admin:
            return error_response(403, "execution_identity_required")
        policy = runtime.snapshot().policy
        permitted = [
            name
            for name, rule in policy.models.items()
            if set(identity.roles).intersection(rule.roles)
        ]
        return JSONResponse(
            content={
                "object": "list",
                "data": [
                    {
                        "id": name,
                        "object": "model",
                        "created": 0,
                        "owned_by": "fastfence-policy",
                    }
                    for name in permitted
                ],
            }
        )

    @router.post("/chat/completions")
    async def complete(request: Request) -> JSONResponse:
        identity = authenticated(runtime, request)
        if identity is None:
            return error_response(401, "authentication_required")
        if identity.admin:
            return error_response(403, "execution_identity_required")
        restore = request.headers.get("x-fastfence-restore-originals", "false")
        if restore not in {"true", "false"}:
            return error_response(422, "invalid_restoration_flag")
        payload = await read_payload(request)
        if isinstance(payload, JSONResponse):
            return payload
        verdict = await runtime.invoke(
            identity, payload.as_model_call(restore_originals=restore == "true")
        )
        return verdict_response(verdict, payload.model)

    return router
