"""Invocation DTOs reject attempts to override trusted authentication or routing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fastfence.modules.control.domain.models import ModelCall, ToolCall


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ToolCall, {"tool": "knowledge.search", "role": "operator"}),
        (ToolCall, {"tool": "knowledge.search", "tenant": "other"}),
        (
            ModelCall,
            {
                "model": "qwen3:0.6b",
                "prompt": "safe",
                "upstream_url": "http://evil",
            },
        ),
    ],
)
def test_invocation_dtos_reject_identity_and_upstream_overrides(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)
