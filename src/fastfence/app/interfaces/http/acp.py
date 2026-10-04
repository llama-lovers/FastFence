"""Bounded synchronous Agent Communication Protocol compatibility ingress."""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.contracts.dto import Identity, ToolCall, Verdict
from fastfence.shared.acp import (
    ACPInput,
    ACPName,
    project_messages,
    restore_messages,
)
from fastfence.shared.request_size import request_size

MAX_BODY_BYTES = 65_536


class RunRequest(ACPInput):
    agent_name: ACPName
    mode: Literal["sync"] = "sync"
    session_id: None = None
    session: None = None


def error_response(status: int, reason: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "code": "not_found" if status == 404 else "invalid_input",
            "message": "FastFence cannot accept this ACP request.",
            "data": {"reason": reason},
        },
    )


def authenticate(
    runtime: ControlRuntime, request: Request
) -> Identity | JSONResponse:
    authorization = request.headers.get("authorization", "")
    identity = runtime.authenticate(
        authorization[7:] if authorization.startswith("Bearer ") else None
    )
    if identity is None:
        return error_response(401, "authentication_required")
    if identity.admin:
        return error_response(403, "execution_identity_required")
    return identity


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


async def read_payload(request: Request) -> RunRequest | JSONResponse:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            return error_response(413, "body_too_large")
        body.extend(chunk)
    try:
        return RunRequest.model_validate(
            json.loads(body, object_pairs_hook=unique_fields)
        )
    except (ValueError, ValidationError, RecursionError):
        return error_response(422, "unsupported_or_invalid_request")


def manifest(name: str) -> dict:
    return {
        "name": name,
        "description": "Protected synchronous text agent routed through FastFence policies.",
        "input_content_types": ["text/plain"],
        "output_content_types": ["text/plain"],
        "metadata": {
            "annotations": {
                "fastfence.modes": ["sync"],
                "fastfence.sessions": False,
                "fastfence.streaming": False,
            }
        },
    }


def run_response(verdict: Verdict, agent: str, created_at: str) -> JSONResponse:
    allowed = verdict.decision in {"allowed", "redacted"}
    output = []
    if allowed:
        try:
            if not isinstance(verdict.output, dict) or set(verdict.output) != {
                "output"
            }:
                raise ValueError
            messages = restore_messages(verdict.output["output"])
            if not messages:
                raise ValueError
            output = messages
        except (ValueError, ValidationError):
            return error_response(503, "invalid_protected_output")
    return JSONResponse(
        headers={
            "X-FastFence-Request-Id": verdict.request_id,
            "X-FastFence-Decision": verdict.decision,
            "X-FastFence-Upstream-Executed": str(
                verdict.upstream_executed
            ).lower(),
            "X-FastFence-Policy-Version": str(verdict.policy_version),
            "X-FastFence-Queue-Wait-Ms": str(verdict.queue_wait_ms),
        },
        content={
            "run_id": str(UUID(hex=verdict.request_id)),
            "agent_name": agent,
            "status": "completed" if allowed else "failed",
            "output": output,
            "created_at": created_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "session_id": None,
            "await_request": None,
            "error": None
            if allowed
            else {
                "code": "server_error"
                if verdict.decision == "error"
                else "invalid_input",
                "message": "FastFence denied or could not complete this run.",
                "data": {
                    "reason": verdict.reason,
                    "request_id": verdict.request_id,
                    "upstream_executed": verdict.upstream_executed,
                    "queue_wait_ms": verdict.queue_wait_ms,
                },
            },
        },
    )


async def execute_run(
    runtime: ControlRuntime, registered: Mapping[str, str], request: Request
) -> JSONResponse:
    identity = authenticate(runtime, request)
    if isinstance(identity, JSONResponse):
        return identity
    payload = await read_payload(request)
    if isinstance(payload, JSONResponse):
        return payload
    tool = registered.get(payload.agent_name)
    if tool is None:
        return error_response(404, "agent_not_available")
    restore = request.headers.get("x-fastfence-restore-originals", "false")
    if restore not in {"true", "false"}:
        return error_response(422, "invalid_restoration_flag")
    created_at = datetime.now(UTC).isoformat()
    verdict = await runtime.invoke(
        identity,
        ToolCall(
            tool=tool,
            arguments={"input": project_messages(payload.input)},
            restore_originals=restore == "true",
        ),
        preparation_bytes=request_size(request.scope),
    )
    return run_response(verdict, payload.agent_name, created_at)


def page_names(
    available: Mapping[str, str], request: Request
) -> list[str] | JSONResponse:
    try:
        limit = int(request.query_params.get("limit", "10"))
        offset = int(request.query_params.get("offset", "0"))
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError
    except ValueError:
        return error_response(422, "invalid_pagination")
    return sorted(available)[offset : offset + limit]


def permitted(
    runtime: ControlRuntime, registered: Mapping[str, str], identity: Identity
) -> dict[str, str]:
    policies = runtime.snapshot().policy.tools
    return {
        name: tool
        for name, tool in registered.items()
        if tool in policies
        and set(identity.roles).intersection(policies[tool].roles)
        and runtime.engine.tools.supports(tool)
    }


def create_router(
    runtime: ControlRuntime, agents: Mapping[str, str]
) -> APIRouter:
    router = APIRouter(
        prefix="/acp", tags=["Protected Agent Communication Protocol"]
    )
    registered = dict(agents)

    @router.get("/ping")
    async def ping(request: Request) -> JSONResponse:
        identity = authenticate(runtime, request)
        return (
            identity if isinstance(identity, JSONResponse) else JSONResponse({})
        )

    @router.get("/agents")
    async def discovery(request: Request) -> JSONResponse:
        identity = authenticate(runtime, request)
        if isinstance(identity, JSONResponse):
            return identity
        names = page_names(permitted(runtime, registered, identity), request)
        if isinstance(names, JSONResponse):
            return names
        return JSONResponse({"agents": [manifest(name) for name in names]})

    @router.get("/agents/{name}")
    async def agent(request: Request, name: str) -> JSONResponse:
        identity = authenticate(runtime, request)
        if isinstance(identity, JSONResponse):
            return identity
        if name not in permitted(runtime, registered, identity):
            return error_response(404, "agent_not_available")
        return JSONResponse(manifest(name))

    @router.post("/runs")
    async def run(request: Request) -> JSONResponse:
        return await execute_run(runtime, registered, request)

    @router.api_route(
        "/{unsupported:path}", methods=["GET", "POST", "PUT", "DELETE"]
    )
    async def unsupported_operation(request: Request) -> JSONResponse:
        identity = authenticate(runtime, request)
        return (
            identity
            if isinstance(identity, JSONResponse)
            else error_response(501, "unsupported_stateless_operation")
        )

    return router
