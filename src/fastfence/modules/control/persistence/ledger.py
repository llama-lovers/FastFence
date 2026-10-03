from __future__ import annotations

import fcntl
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastfence.modules.control.domain.exceptions import BudgetExceededError
from fastfence.modules.control.domain.models import Limits, Verdict


class Ledger:
    """Durable single-host ledger. BEGIN IMMEDIATE serializes competing reservations."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._process_lock = (path.parent / "ledger.lock").open("a")
        try:
            fcntl.flock(self._process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._process_lock.close()
            raise RuntimeError(
                "Another gateway owns this state directory; use one worker"
            ) from None
        self._closed = False
        self._lock = threading.RLock()
        self.db = sqlite3.connect(
            path, check_same_thread=False, isolation_level=None
        )
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS budgets (
                day TEXT, subject TEXT, calls INTEGER DEFAULT 0,
                tokens INTEGER DEFAULT 0, cost_microusd INTEGER DEFAULT 0,
                compute_ms INTEGER DEFAULT 0, inflight INTEGER DEFAULT 0,
                PRIMARY KEY (day, subject)
            );
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY, day TEXT, subject TEXT,
                tokens INTEGER, cost_microusd INTEGER, compute_ms INTEGER,
                settled INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT, subject TEXT, tenant TEXT, target TEXT, record TEXT
            );
        """)
        # Unsettled reservations remain fully charged after a crash. Release only concurrency.
        with self._lock:
            self.db.execute("UPDATE reservations SET settled=1 WHERE settled=0")
            self.db.execute("UPDATE budgets SET inflight=0")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            self.db.close()
            fcntl.flock(self._process_lock, fcntl.LOCK_UN)
            self._process_lock.close()

    @staticmethod
    def day() -> str:
        return datetime.now(UTC).date().isoformat()

    def reserve(
        self,
        request_id: str,
        subject: str,
        limits: Limits,
        tokens: int,
        cost: int,
        ms: int,
    ) -> None:
        day = self.day()
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute(
                    "INSERT OR IGNORE INTO budgets(day, subject) VALUES (?, ?)",
                    (day, subject),
                )
                row = self.db.execute(
                    "SELECT * FROM budgets WHERE day=? AND subject=?",
                    (day, subject),
                ).fetchone()
                checks = {
                    "calls": (1, limits.calls),
                    "tokens": (tokens, limits.tokens),
                    "cost_microusd": (cost, limits.cost_microusd),
                    "compute_ms": (ms, limits.compute_ms),
                    "inflight": (1, limits.concurrent),
                }
                for field, (additional, maximum) in checks.items():
                    if row[field] + additional > maximum:
                        raise BudgetExceededError(f"budget_{field}")
                self.db.execute(
                    "UPDATE budgets SET calls=calls+1,tokens=tokens+?,cost_microusd=cost_microusd+?,"
                    "compute_ms=compute_ms+?,inflight=inflight+1 WHERE day=? AND subject=?",
                    (tokens, cost, ms, day, subject),
                )
                self.db.execute(
                    "INSERT INTO reservations(id,day,subject,tokens,cost_microusd,compute_ms) "
                    "VALUES (?,?,?,?,?,?)",
                    (request_id, day, subject, tokens, cost, ms),
                )
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def settle(
        self, request_id: str, tokens: int, cost: int, compute_ms: int
    ) -> None:
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT * FROM reservations WHERE id=? AND settled=0",
                    (request_id,),
                ).fetchone()
                if row:
                    # The adapter must bound consumption before invocation. Never refund overruns.
                    tokens = max(0, min(tokens, row["tokens"]))
                    cost = max(0, min(cost, row["cost_microusd"]))
                    compute_ms = max(0, min(compute_ms, row["compute_ms"]))
                    self.db.execute(
                        "UPDATE budgets SET tokens=tokens-?+?,cost_microusd=cost_microusd-?+?,"
                        "compute_ms=compute_ms-?+?,inflight=inflight-1 WHERE day=? AND subject=?",
                        (
                            row["tokens"],
                            tokens,
                            row["cost_microusd"],
                            cost,
                            row["compute_ms"],
                            compute_ms,
                            row["day"],
                            row["subject"],
                        ),
                    )
                    self.db.execute(
                        "UPDATE reservations SET settled=1 WHERE id=?",
                        (request_id,),
                    )
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def append(
        self, subject: str, tenant: str, target: str, verdict: Verdict
    ) -> None:
        # Request/response bodies, auth tokens, resources and provider errors are never persisted.
        data = verdict.model_dump(exclude={"output"})
        with self._lock:
            self.db.execute(
                "INSERT INTO audit(time,subject,tenant,target,record) VALUES(?,?,?,?,?)",
                (
                    datetime.now(UTC).isoformat(),
                    subject,
                    tenant,
                    target,
                    json.dumps(data),
                ),
            )

    def audit(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT * FROM audit ORDER BY sequence DESC LIMIT ?",
                (min(limit, 10_000),),
            ).fetchall()
        return [
            dict(
                sequence=r["sequence"],
                time=r["time"],
                subject=r["subject"],
                tenant=r["tenant"],
                target=r["target"],
                **json.loads(r["record"]),
            )
            for r in rows
        ]

    def budgets(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM budgets WHERE day=? ORDER BY subject",
                    (self.day(),),
                )
            ]

    def stats(self) -> dict[str, int]:
        with self._lock:
            rows = self.db.execute("SELECT record FROM audit").fetchall()
        records = [json.loads(row[0]) for row in rows]
        latencies = sorted(r["latency_ms"] for r in records)
        return {
            "requests": len(records),
            "allowed": sum(r["decision"] == "allowed" for r in records),
            "blocked": sum(r["decision"] == "blocked" for r in records),
            "redacted": sum(r["decision"] == "redacted" for r in records),
            "errors": sum(r["decision"] == "error" for r in records),
            "p95_latency_ms": latencies[
                min(len(latencies) - 1, int(len(latencies) * 0.95))
            ]
            if latencies
            else 0,
        }
