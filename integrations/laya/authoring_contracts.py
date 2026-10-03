"""Strict rule-authoring records, origin checks, and proposal parsing."""

from __future__ import annotations

import argparse
import ipaddress
import json
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

if __package__:
    from .run_demo import UPSTREAM_COMMIT
else:
    from run_demo import UPSTREAM_COMMIT


class AuthoringError(Exception):
    """Expose stable failure codes without model text or credential values."""


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    supported: bool
    rule: dict[str, Any] | None


class AuthoringReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upstream_commit: str = UPSTREAM_COMMIT
    model: str | None
    authoring_source: Literal["real_laya", "reviewed_proposal"]
    status: str
    rule_id: str
    operator: str
    direction: str
    target: str
    sample_count: int
    matches: list[bool]
    inference_ms: int = Field(ge=0)
    activated: bool
    policy_version: int
    scope: str = "Real Laya/local-model management authoring; no protected-call inference"


def local_url(value: str) -> str:
    parts = urlsplit(value)
    try:
        loopback = (
            parts.hostname == "localhost"
            or ipaddress.ip_address(parts.hostname or "").is_loopback
        )
    except ValueError:
        loopback = False
    if (
        parts.scheme not in {"http", "https"}
        or not loopback
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise argparse.ArgumentTypeError(
            "Use a loopback HTTP(S) origin without credentials"
        )
    try:
        _ = parts.port
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid local origin port") from None
    return value.rstrip("/")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthoringError("duplicate_model_json_key")
        result[key] = value
    return result


def parse_proposal(content: str, direction: str, target: str) -> dict[str, Any]:
    if len(content.encode()) > 16_384:
        raise AuthoringError("model_proposal_too_large")
    try:
        proposal = Proposal.model_validate(
            json.loads(content, object_pairs_hook=unique_object)
        )
    except (ValueError, TypeError):
        raise AuthoringError("invalid_model_proposal") from None
    if not proposal.supported or proposal.rule is None:
        raise AuthoringError("unsupported_or_ambiguous_instruction")
    if (
        proposal.rule.get("direction") != direction
        or proposal.rule.get("target") != target
    ):
        raise AuthoringError("model_changed_requested_scope")
    return proposal.rule


async def prepare_ollama_options(
    prepare: Callable[..., Awaitable[Any]], **kwargs: Any
) -> Any:
    """Adapt actual Laya request options to Ollama's supported thinking switch."""
    model, options, metadata = await prepare(**kwargs)
    options = {
        **options,
        "extra_body": {
            **options.get("extra_body", {}),
            "reasoning_effort": "none",
        },
    }
    return model, options, metadata


def constrained_rule_schema(
    schema: dict[str, Any], direction: str, target: str
) -> dict[str, Any]:
    """Constrain generation scope while retaining independent server validation."""
    properties = dict(schema["properties"])
    for name, value in {"direction": direction, "target": target}.items():
        original = properties[name]
        if value not in original["enum"]:
            raise AuthoringError("invalid_requested_scope")
        properties[name] = {**original, "enum": [value], "default": value}
    return {**schema, "properties": properties, "required": list(properties)}
