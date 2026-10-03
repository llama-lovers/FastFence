from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from fastfence.core.schema import Limits, ToolCall
from fastfence.data.ledger import BudgetExceeded, Ledger


def limits(**changes):
    return Limits(
        calls=changes.get("calls", 20),
        tokens=changes.get("tokens", 100000),
        cost_microusd=changes.get("cost_microusd", 10000),
        compute_ms=changes.get("compute_ms", 10000),
        concurrent=changes.get("concurrent", 20),
    )


@pytest.mark.parametrize(
    "field,amount,reason",
    [
        ("calls", 1, "budget_calls"),
        ("tokens", 5, "budget_tokens"),
        ("cost_microusd", 5, "budget_cost_microusd"),
        ("compute_ms", 5, "budget_compute_ms"),
        ("concurrent", 1, "budget_inflight"),
    ],
)
def test_each_limit_is_enforced_before_spend(tmp_path, field, amount, reason):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    rule = limits(**{field: amount})
    ledger.reserve("first", "subject", rule, 5, 5, 5)
    with pytest.raises(BudgetExceeded, match=reason):
        ledger.reserve("second", "subject", rule, 5, 5, 5)
    assert ledger.budgets()[0]["calls"] == 1
    ledger.close()


def test_atomic_parallel_reservations_never_overspend(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    rule = limits(calls=4, tokens=100, concurrent=4)

    def reserve(i):
        try:
            ledger.reserve(str(i), "actor", rule, 25, 0, 10)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(reserve, range(40)))
    assert sum(results) == 4
    row = ledger.budgets()[0]
    assert row["calls"] == 4 and row["tokens"] == 100 and row["inflight"] == 4
    ledger.close()


def test_settlement_releases_unused_reservation_and_is_idempotent(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.reserve("r", "actor", limits(), 100, 100, 100)
    ledger.settle("r", 20, 30, 40)
    ledger.settle("r", 0, 0, 0)
    row = ledger.budgets()[0]
    assert (
        row["calls"],
        row["tokens"],
        row["cost_microusd"],
        row["compute_ms"],
        row["inflight"],
    ) == (1, 20, 30, 40, 0)
    ledger.close()


def test_crash_recovery_retains_full_charge_and_refuses_second_owner(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    first = Ledger(path)
    first.reserve("r", "actor", limits(), 100, 100, 100)
    with pytest.raises(RuntimeError, match="Another gateway"):
        Ledger(path)
    first.close()
    recovered = Ledger(path)
    row = recovered.budgets()[0]
    assert row["tokens"] == 100 and row["cost_microusd"] == 100 and row["inflight"] == 0
    recovered.close()


async def test_parallel_engine_calls_enforce_limit_before_upstream(app, tokens, monkeypatch):
    engine = app.state.engine
    policy = engine.policies.snapshot().policy
    policy.version += 1
    policy.budgets["analyst"].calls = 3
    engine.policies.save(policy)
    upstream_count = 0
    original = engine.tools.call

    async def counted(*args):
        nonlocal upstream_count
        upstream_count += 1
        await asyncio.sleep(0.03)
        return await original(*args)

    monkeypatch.setattr(engine.tools, "call", counted)
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    results = await asyncio.gather(
        *(
            engine.invoke(identity, ToolCall(tool="knowledge.search", arguments={"query": "safe"}))
            for _ in range(12)
        )
    )
    assert upstream_count == 3
    assert sum(r.decision == "allowed" for r in results) == 3
    assert sum(r.reason == "budget_calls" for r in results) == 9
    assert engine.ledger.budgets()[0]["inflight"] == 0
    engine.ledger.close()
