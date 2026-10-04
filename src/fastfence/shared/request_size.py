"""Account transport-retained bytes without coupling the core to HTTP."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


class RequestBytes(BaseModel):
    received: int = Field(default=0, ge=0)


def request_size(scope: Mapping[str, Any]) -> int:
    value = scope.get("fastfence.request_bytes", 0)
    if isinstance(value, RequestBytes):
        return value.received
    return value if type(value) is int and value >= 0 else 0
