"""A privacy transformation must not introduce forbidden forwarded content."""

import json

import pytest

from fastfence.modules.control.application.use_cases.policy_preview import (
    PolicySample,
    preview_sample,
)
from fastfence.modules.control.domain.models import ModelCall, ToolCall
from tests.fixtures.policy import configure_policy

SENSITIVE = "12345678901"


def configure(engine, project, restriction, direction, target, value="a"):
    def change(data):
        data["privacy"].update(input="redact", output="redact")
        data["text_rules"] = (
            [
                {
                    "id": "forbidden-letter",
                    "operator": "word_contains",
                    "value": value,
                    "direction": direction,
                    "target": target,
                }
            ]
            if restriction == "text"
            else []
        )

    configure_policy(engine, change)
    if restriction == "signature":
        feed = engine.policies.snapshot().feed.editable()
        feed["version"] += 1
        feed["signatures"].append(
            {
                "id": "forbidden-marker",
                "pattern": "[REDACTED:pii_polish_id]",
                "description": "Test policy forbids this generated marker",
            }
        )
        (project / "config/signatures.json").write_text(json.dumps(feed))
        engine.policies.reload()


@pytest.mark.parametrize("target", ["model", "tool"])
@pytest.mark.parametrize("direction", ["input", "output"])
@pytest.mark.parametrize("restriction", ["text", "signature"])
async def test_redaction_cannot_bypass_restrictions(
    app, tokens, project, monkeypatch, target, direction, restriction
):
    engine = app.state.engine
    configure(engine, project, restriction, direction, target)
    calls = []

    async def model(*args, **kwargs):
        calls.append(args)
        return {"text": SENSITIVE}, 5

    async def tool(*args):
        calls.append(args)
        return {"text": SENSITIVE}

    monkeypatch.setattr(engine.models, "complete", model)
    monkeypatch.setattr(engine.tools, "call", tool)
    text = SENSITIVE if direction == "input" else "tiny"
    call = (
        ModelCall(model="qwen3:0.6b", prompt=text)
        if target == "model"
        else ToolCall(tool="knowledge.search", arguments={"query": text})
    )
    verdict = await engine.invoke(
        app.state.identities.authenticate(tokens["analyst-blue"]), call
    )
    assert verdict.decision == "blocked" and verdict.output is None
    reason = (
        f"{direction}_text_rule"
        if restriction == "text"
        else "attack_signature"
        if direction == "input"
        else "output_attack_signature"
    )
    assert verdict.reason == reason
    assert verdict.upstream_executed == (direction == "output")
    assert len(calls) == int(direction == "output")
    assert "pii_polish_id" in verdict.findings
    assert (
        "forbidden-letter" if restriction == "text" else "forbidden-marker"
    ) in verdict.findings
    if direction == "input":
        assert engine.ledger.budgets() == []
    else:
        assert all(row["inflight"] == 0 for row in engine.ledger.budgets())
    audit = engine.ledger.audit()
    assert audit[-1]["reason"] == reason
    assert SENSITIVE not in json.dumps(audit)
    sample = preview_sample(
        engine.policies.snapshot(),
        PolicySample(text=SENSITIVE, direction=direction, target=target),
        0,
        engine.secrets,
    )
    assert sample.decision == "blocked" and sample.reason == reason
    assert set(sample.findings) == set(verdict.findings)


@pytest.mark.parametrize("direction", ["input", "output"])
async def test_nonconflicting_redaction_still_delivers_safe_content(
    app, tokens, project, monkeypatch, direction
):
    engine = app.state.engine
    configure(engine, project, "text", direction, "model", value="z")
    received = []

    async def model(model, prompt, maximum, timeout, **kwargs):
        received.append(prompt)
        return {"text": SENSITIVE if direction == "output" else "tiny"}, 5

    monkeypatch.setattr(engine.models, "complete", model)
    verdict = await engine.invoke(
        app.state.identities.authenticate(tokens["analyst-blue"]),
        ModelCall(
            model="qwen3:0.6b",
            prompt=SENSITIVE if direction == "input" else "tiny",
        ),
    )
    assert verdict.decision == "redacted" and verdict.upstream_executed
    assert len(received) == 1
    assert SENSITIVE not in received[0]
    assert SENSITIVE not in json.dumps(verdict.output)
    assert all(row["inflight"] == 0 for row in engine.ledger.budgets())
