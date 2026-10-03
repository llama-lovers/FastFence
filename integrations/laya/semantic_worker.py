"""Persistent, database-free embedding of the pinned real Laya model client.

Only Laya's application audit/budget hooks are replaced: FastFence owns those
controls. Inference always executes the upstream llm_call and provider transport.
No text, conversation, settings file or SQLite database is written by this worker.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import sys
from functools import partial
from pathlib import Path
from typing import Any

from authoring_contracts import local_url, prepare_ollama_options, unique_object
from pydantic import BaseModel, ConfigDict, Field
from semantic_response import install_provider_validation

UPSTREAM_COMMIT = "b3b998c03dc44076675305581eb4640b9bf6ff8f"


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=65_536)
    system: str = Field(max_length=16_384)
    schema_: dict[str, Any] = Field(alias="schema")
    timeout_ms: int = Field(ge=100, le=60_000)


async def owned_by_fastfence(*args: Any, **kwargs: Any) -> None:
    """FastFence accounts usage and writes sanitized audit records itself."""


def database_forbidden(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("SQLite is not permitted in the semantic worker")


async def initialize(source: Path, url: str) -> tuple[Any, dict[str, Any]]:
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(source),
        "rev-parse",
        "HEAD",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode or stdout.decode().strip() != UPSTREAM_COMMIT:
        raise RuntimeError("Laya revision mismatch")
    sys.path.insert(0, str(source / "engine"))
    import sqlite3

    import structlog

    sqlite3.connect = database_forbidden
    logging.disable(100)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL)
    )
    install_provider_validation()
    from laya import config
    from laya.llm import client, providers
    from laya.pipeline import budget, queue

    settings = {
        "models": {"chat": "fastfence/qwen3:0.6b"},
        "custom_providers": [
            {
                "id": "fastfence",
                "provider_type": "openai_compatible",
                "base_url": url,
                "default_timeout": 60,
                "capabilities_override": {
                    "supports_tool_calling": False,
                    "supports_structured_output": True,
                    "supports_reasoning": True,
                },
            }
        ],
        "pipeline": {"model_timeout": 60, "llm_retries": 1},
    }

    # Supply deployment settings from memory. No Laya settings file is needed.
    def current_settings() -> dict[str, Any]:
        return copy.deepcopy(settings)

    for module in (config, client, providers, queue):
        module.load_settings = current_settings
    client.log_to_audit = owned_by_fastfence
    budget.check_budget = owned_by_fastfence
    client._prepare_call_kwargs = partial(
        prepare_ollama_options, client._prepare_call_kwargs
    )
    return client, settings


async def assess(
    client: Any, settings: dict[str, Any], request: Request
) -> dict[str, Any]:
    settings["models"]["chat"] = "fastfence/" + request.model
    settings["pipeline"]["model_timeout"] = request.timeout_ms / 1000
    settings["custom_providers"][0]["default_timeout"] = (
        request.timeout_ms / 1000
    )
    response = await client.llm_call(
        role="chat",
        messages=[
            {"role": "system", "content": request.system},
            {"role": "user", "content": "DATA:\n" + request.text},
        ],
        response_schema={
            "name": "fastfence_security_severity",
            "schema": request.schema_,
        },
        temperature=0,
        max_tokens=64,
        num_retries=1,
        step="fastfence_semantic_inspection",
    )
    if (
        response.truncated
        or response.finish_reason != "stop"
        or response.tool_calls
    ):
        raise ValueError("Incomplete classifier response")
    if len(response.content.encode()) > 1024:
        raise ValueError("Classifier response too large")
    return {
        "source": "real_laya",
        "content": response.content,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


async def serve(args: argparse.Namespace, output: Any) -> None:
    client, settings = await initialize(args.source, args.ollama_url)
    from laya.http_client import close_client
    from laya.tasks import cancel_all

    try:
        while raw := await asyncio.to_thread(
            sys.stdin.buffer.readline, 524_289
        ):
            try:
                if len(raw) > 524_288 or not raw.endswith(b"\n"):
                    raise ValueError("Request too large")
                request = Request.model_validate(
                    json.loads(raw, object_pairs_hook=unique_object)
                )
                async with asyncio.timeout(request.timeout_ms / 1000):
                    result = await assess(client, settings, request)
            except Exception:
                result = {"error": "laya_semantic_unavailable"}
            output.write(json.dumps(result) + "\n")
            output.flush()
    finally:
        await cancel_all()
        await close_client()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--ollama-url", type=local_url, required=True)
    args = parser.parse_args()
    output = sys.stdout
    sys.stdout = (
        sys.stderr
    )  # Third-party diagnostics can never enter the protocol.
    try:
        asyncio.run(serve(args, output))
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
