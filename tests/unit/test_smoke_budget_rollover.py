"""Acceptance retries only a demonstrated UTC-day rollover, never other failures."""

import pytest

from scripts import smoke_uv_tool as smoke


def scenario(
    monkeypatch,
    *,
    rollover=False,
    missing=False,
    bad_count=False,
    restart=False,
):
    state = {
        "day": "2026-10-03",
        "calls": 2,
        "limit": 100,
        "version": 3,
        "rolled": False,
        "invocations": 0,
    }
    monkeypatch.setattr(smoke, "utc_day", lambda: state["day"])

    def status():
        rows = (
            []
            if missing or state["calls"] == 0
            else [
                {
                    "subject": "local-agent",
                    "day": state["day"],
                    "calls": state["calls"],
                    "roles": ["analyst"],
                }
            ]
        )
        return {
            "runtime": {"instance_id": "changed" if restart else "same"},
            "budgets": rows,
        }

    def invoke():
        state["invocations"] += 1
        denied = state["calls"] >= state["limit"]
        if not denied:
            state["calls"] += 2 if bad_count else 1
        verdict = {
            "decision": "blocked" if denied else "allowed",
            "reason": "budget_calls" if denied else "allowed",
            "policy_version": state["version"],
            "upstream_executed": not denied,
            "semantic_input_status": "not_run" if denied else "passed",
            "semantic_output_status": "not_run" if denied else "passed",
            "output": {"text": "synthetic"},
        }
        if rollover and state["invocations"] == 2:
            state.update(day="2026-10-04", calls=0, rolled=True)
        return verdict

    def activate(edit):
        policy = {"budgets": {"analyst": {"calls": state["limit"]}}}
        edit(policy)
        state["limit"] = policy["budgets"]["analyst"]["calls"]
        state["version"] += 1
        return state["version"]

    return state, status, invoke, activate


def test_same_day_sequence_keeps_exact_accounting(monkeypatch):
    state, status, invoke, activate = scenario(monkeypatch)
    assert (
        smoke.check_budget_sequence(
            status, invoke, activate, "same", state["day"]
        )
        == 2
    )
    assert state["calls"] == 3 and state["invocations"] == 2


def test_midnight_after_allowed_call_reseeds_and_rechecks_once(monkeypatch):
    state, status, invoke, activate = scenario(monkeypatch, rollover=True)
    assert (
        smoke.check_budget_sequence(
            status, invoke, activate, "same", state["day"]
        )
        == 1
    )
    assert state["calls"] == 2 and state["invocations"] == 5
    assert state["version"] == 7


@pytest.mark.parametrize(
    "option,error",
    [
        ("missing", RuntimeError),
        ("bad_count", AssertionError),
        ("restart", AssertionError),
    ],
)
def test_non_rollover_failures_are_not_retried(monkeypatch, option, error):
    state, status, invoke, activate = scenario(monkeypatch, **{option: True})
    with pytest.raises(error):
        smoke.check_budget_sequence(
            status, invoke, activate, "same", state["day"]
        )
    assert state["invocations"] <= 2


def test_second_rollover_fails_bounded(monkeypatch):
    state, status, invoke, activate = scenario(monkeypatch, rollover=True)

    def invoke_twice():
        verdict = invoke()
        if state["invocations"] == 3:
            state.update(day="2026-10-05", calls=0)
        return verdict

    with pytest.raises(RuntimeError, match="changed twice"):
        smoke.check_budget_sequence(
            status, invoke_twice, activate, "same", state["day"]
        )
    assert state["invocations"] == 3
