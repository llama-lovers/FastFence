from __future__ import annotations

import json

import httpx
import pytest

from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.modules.control.persistence.models import SemanticScanner
from fastfence.modules.control.persistence.semantic_severity import (
    severity_score,
)


@pytest.mark.parametrize(
    ("category", "score"),
    [("benign", 0.0), ("suspicious", 0.6), ("malicious", 1.0)],
)
def test_categories_are_fixed_ordinal_policy_codes(category, score):
    assert severity_score(json.dumps({"severity": category})) == score


@pytest.mark.parametrize(
    "content",
    [
        '{"severity":"unknown"}',
        '{"severity":true}',
        '{"severity":0.6}',
        '{"severity":"benign","explanation":"private-marker"}',
        '{"severity":"malicious","severity":"benign"}',
        '{"risk":0}',
        '["benign"]',
        '```json\n{"severity":"benign"}\n```',
        "x" * 1025,
    ],
)
async def test_invalid_or_repaired_severity_responses_fail_closed(
    monkeypatch, content
):
    def respond(request):
        return httpx.Response(200, json={"message": {"content": content}})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    with pytest.raises(ModelUnavailableError) as error:
        await SemanticScanner("http://local", "http://local").assess(
            "private text", SemanticConfig(provider="ollama")
        )
    assert "private-marker" not in str(error.value)
    assert "private text" not in str(error.value)


async def test_truncated_valid_looking_category_fails_closed(monkeypatch):
    def respond(request):
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"severity":"benign"}'},
                "done_reason": "length",
            },
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    with pytest.raises(ModelUnavailableError):
        await SemanticScanner("http://local", "http://local").assess(
            "ordinary report", SemanticConfig(provider="ollama")
        )
