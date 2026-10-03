from __future__ import annotations

import asyncio
import json

import pytest

from fastfence.modules.control.domain.models import ModelCall
from tests.fixtures.policy import configure_policy
from tests.fixtures.secrets import GITHUB_FIXTURE, SLACK_FIXTURE


def actor(app, tokens):
    return app.state.identities.authenticate(tokens["analyst-blue"])


@pytest.mark.parametrize(
    "secret",
    [
        GITHUB_FIXTURE,
        SLACK_FIXTURE,
        GITHUB_FIXTURE.translate(
            {code: code + 0xFEE0 for code in range(33, 127)}
        ),
        GITHUB_FIXTURE[:22] + "\n" + GITHUB_FIXTURE[22:],
    ],
)
async def test_detector_blocks_input_before_upstream_and_audit_never_retains_secret(
    app, tokens, monkeypatch, secret
):
    engine = app.state.engine
    calls = []

    async def complete(*args, **kwargs):
        calls.append(args)
        return {"text": "ordinary report"}, 5

    monkeypatch.setattr(engine.models, "complete", complete)
    verdict = await engine.invoke(
        actor(app, tokens),
        ModelCall(model="qwen3:0.6b", prompt=f"Please inspect {secret}"),
    )
    assert verdict.decision == "blocked"
    assert verdict.reason == "input_sensitive_data"
    assert not verdict.upstream_executed and calls == []
    assert verdict.findings and engine.ledger.budgets() == []
    assert secret not in json.dumps(verdict.model_dump())
    assert secret not in json.dumps(engine.ledger.audit())


@pytest.mark.parametrize("action", ["redact", "block"])
async def test_detector_output_policy_applies_after_upstream(
    app, tokens, monkeypatch, action
):
    engine = app.state.engine
    configure_policy(engine, lambda data: data["privacy"].update(output=action))

    async def complete(*args, **kwargs):
        return {"text": f"Report {SLACK_FIXTURE}"}, 5

    monkeypatch.setattr(engine.models, "complete", complete)
    verdict = await engine.invoke(
        actor(app, tokens),
        ModelCall(model="qwen3:0.6b", prompt="Please show the report"),
    )
    assert verdict.upstream_executed and verdict.findings
    assert verdict.decision == ("redacted" if action == "redact" else "blocked")
    assert (verdict.output is None) == (action == "block")
    assert SLACK_FIXTURE not in json.dumps(verdict.model_dump())
    assert SLACK_FIXTURE not in json.dumps(engine.ledger.audit())


async def test_input_redaction_forwards_safe_content_to_real_model_boundary(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    configure_policy(
        engine, lambda data: data["privacy"].update(input="redact")
    )
    calls = []

    async def complete(model, prompt, maximum, timeout, **kwargs):
        calls.append(prompt)
        return {"text": "ordinary response"}, 5

    monkeypatch.setattr(engine.models, "complete", complete)
    result = await engine.invoke(
        actor(app, tokens),
        ModelCall(model="qwen3:0.6b", prompt=f"Inspect {GITHUB_FIXTURE}"),
    )
    assert result.decision == "redacted" and len(calls) == 1
    assert GITHUB_FIXTURE not in calls[0]


async def test_disabling_privacy_disables_detector_without_hidden_scanning(
    app, tokens, monkeypatch
):
    engine = app.state.engine
    configure_policy(engine, lambda data: data["privacy"].update(enabled=False))
    calls = []

    def forbidden(value):
        raise AssertionError("Disabled privacy unexpectedly invoked detector")

    async def complete(model, prompt, maximum, timeout, **kwargs):
        calls.append(prompt)
        return {"text": SLACK_FIXTURE}, 5

    monkeypatch.setattr(engine.secrets, "redact", forbidden)
    monkeypatch.setattr(engine.models, "complete", complete)
    result = await engine.invoke(
        actor(app, tokens),
        ModelCall(model="qwen3:0.6b", prompt=GITHUB_FIXTURE),
    )
    assert result.decision == "allowed" and result.findings == []
    assert calls == [GITHUB_FIXTURE]
    assert result.output == {"text": SLACK_FIXTURE}


@pytest.mark.parametrize("direction", ["input", "output"])
async def test_detector_exception_fails_closed_and_never_leaks_error_contents(
    app, tokens, monkeypatch, direction
):
    engine = app.state.engine
    detector = engine.secrets.redact
    scans = 0
    calls = []

    def broken(value):
        nonlocal scans
        scans += 1
        if scans == (1 if direction == "input" else 2):
            raise RuntimeError(f"private detector failure {GITHUB_FIXTURE}")
        return detector(value)

    async def complete(*args, **kwargs):
        calls.append(args)
        return {"text": "ordinary response"}, 5

    monkeypatch.setattr(engine.secrets, "redact", broken)
    monkeypatch.setattr(engine.models, "complete", complete)
    result = await engine.invoke(
        actor(app, tokens),
        ModelCall(model="qwen3:0.6b", prompt="Please inspect this report"),
    )
    assert result.decision == "blocked" and result.output is None
    assert result.reason == f"{direction}_secret_detector_unavailable"
    assert result.upstream_executed == (direction == "output")
    assert len(calls) == (1 if direction == "output" else 0)
    assert GITHUB_FIXTURE not in json.dumps(result.model_dump())
    assert "private detector failure" not in json.dumps(engine.ledger.audit())
    assert all(budget["inflight"] == 0 for budget in engine.ledger.budgets())


async def test_shared_detector_keeps_concurrent_decisions_isolated(
    app, tokens, monkeypatch
):
    engine = app.state.engine

    async def complete(*args, **kwargs):
        await asyncio.sleep(0)
        return {"text": "ordinary response"}, 5

    monkeypatch.setattr(engine.models, "complete", complete)
    prompts = [GITHUB_FIXTURE, "ordinary report", SLACK_FIXTURE] * 2
    results = await asyncio.gather(
        *[
            engine.invoke(
                actor(app, tokens),
                ModelCall(model="qwen3:0.6b", prompt=prompt),
            )
            for prompt in prompts
        ]
    )
    assert [result.decision for result in results] == [
        "blocked",
        "allowed",
        "blocked",
        "blocked",
        "allowed",
        "blocked",
    ]
    assert engine.ledger.stats()["requests"] == 6
    assert engine.ledger.budgets()[0]["inflight"] == 0
