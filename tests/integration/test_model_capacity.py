"""Local queue saturation has a distinct sanitized, fail-closed public reason."""

import json

import pytest

from fastfence.modules.control.domain.exceptions import (
    ModelCapacityExceededError,
    ModelUnavailableError,
)
from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.modules.control.persistence.laya_semantic import (
    MAX_PENDING_ASSESSMENTS,
    WorkerResult,
)
from fastfence.modules.control.persistence.model_http import (
    MAX_PENDING_REQUESTS,
)
from fastfence.modules.control.persistence.models import (
    OllamaModels,
    SemanticScanner,
)
from fastfence.modules.control.persistence.openai_models import OpenAIModels
from tests.fixtures.auth import headers
from tests.fixtures.policy import configure_policy


@pytest.mark.parametrize("kind", ["native", "openai", "ollama", "kev", "laya"])
async def test_adapters_preserve_capacity_and_distinguish_closed(
    kind, tmp_path
):
    scanner = kind in {"ollama", "kev", "laya"}
    adapter = (
        SemanticScanner("http://localhost:1", "http://localhost:2", tmp_path)
        if scanner
        else (
            OllamaModels("http://localhost:1")
            if kind == "native"
            else OpenAIModels("http://localhost:1/v1")
        )
    )
    queue = adapter.laya if kind == "laya" else adapter._http
    queue._pending = (
        MAX_PENDING_ASSESSMENTS if kind == "laya" else MAX_PENDING_REQUESTS
    )

    async def call():
        if scanner:
            return await adapter.assess(
                "synthetic private input", SemanticConfig(provider=kind)
            )
        return await adapter.complete(
            "fixture", "synthetic private input", 10, 1000
        )

    try:
        with pytest.raises(
            ModelCapacityExceededError, match="^Model capacity exceeded$"
        ):
            await call()
        assert adapter._http._client is None
        queue._closed = True
        with pytest.raises(ModelUnavailableError) as caught:
            await call()
        assert not isinstance(caught.value, ModelCapacityExceededError)
        assert "synthetic private input" not in str(caught.value)
    finally:
        queue._pending = 0
        await adapter.aclose()


@pytest.mark.parametrize(
    "stage", ["input", "business", "business_semantic", "output"]
)
def test_http_capacity_is_503_with_settled_private_audit(
    client, app, tokens, monkeypatch, stage
):
    engine = app.state.engine
    scanner = engine.scanner
    upstream_calls = []

    def configure(data):
        data["models"]["qwen3:0.6b"]["cost_microusd"] = 123
        if stage != "business":
            data["semantic"].update(provider="laya")

    configure_policy(engine, configure)
    if stage == "input":
        scanner.laya._pending = MAX_PENDING_ASSESSMENTS
    elif stage.startswith("business"):
        engine.models._http._pending = MAX_PENDING_REQUESTS

    async def assessed(*args):
        return WorkerResult(
            source="real_laya",
            content='{"severity":"benign"}',
            input_tokens=1,
            output_tokens=1,
        )

    async def complete(*args, **kwargs):
        upstream_calls.append(args)
        scanner.laya._pending = MAX_PENDING_ASSESSMENTS
        return {"text": "synthetic private output"}, 200

    monkeypatch.setattr(scanner.laya, "_exchange", assessed)
    if not stage.startswith("business"):
        monkeypatch.setattr(engine.models, "complete", complete)
    response = client.post(
        "/v1/chat/completions",
        headers=headers(tokens),
        json={
            "model": "qwen3:0.6b",
            "messages": [
                {"role": "user", "content": "synthetic private input"}
            ],
            "max_tokens": 64,
        },
    )
    scanner.laya._pending = 0
    engine.models._http._pending = 0
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_capacity_exceeded"
    assert "synthetic private" not in response.text
    audit = engine.ledger.audit()[0]
    assert audit["decision"] == "error"
    assert audit["reason"] == "model_capacity_exceeded"
    assert audit["upstream_executed"] is (stage == "output")
    assert "synthetic private" not in json.dumps(audit)
    assert len(upstream_calls) == (1 if stage == "output" else 0)
    budget = engine.ledger.budgets()[0]
    assert budget["inflight"] == 0 and budget["calls"] == 1
    assert budget["tokens"] == audit["tokens"] > 0
    input_units = len(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "synthetic private input"}
                ]
            },
            separators=(",", ":"),
        ).encode()
    )
    semantic_units = input_units + 1024
    expected_tokens = {
        "input": input_units,
        "business": input_units,
        "business_semantic": input_units + semantic_units,
        "output": 200 + semantic_units,
    }[stage]
    assert budget["tokens"] == expected_tokens
    assert (
        budget["cost_microusd"]
        == audit["cost_microusd"]
        == (123 if stage == "output" else 0)
    )
    stats = engine.ledger.stats()
    assert stats["errors"] == stats["requests"] == 1
    assert stats["blocked"] == 0
    assert (
        stats["semantic_calls"]
        == {"input": 1, "business": 0, "business_semantic": 1, "output": 2}[
            stage
        ]
    )
    assert stats["semantic_requests"] == (stage != "business")
    if stage == "input":
        assert audit["semantic_input_status"] == "error"
        assert audit["semantic_output_status"] == "not_run"
    elif stage == "output":
        assert audit["semantic_input_status"] == "passed"
        assert audit["semantic_output_status"] == "error"
