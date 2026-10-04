"""Bounded comparison and one-use, owner-bound activation receipts."""

import asyncio
import hashlib
import secrets
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastfence.app.interfaces.http.authoring_regression import (
    policy_digest,
    yaml_diff,
)
from fastfence.app.interfaces.http.semantic_review_evaluation import (
    candidate_policy,
    evaluate_case,
)
from fastfence.app.interfaces.http.semantic_review_models import (
    RuleCase,
    SemanticActivateRequest,
    SemanticCaseResult,
    SemanticOutcome,
    SemanticReceipt,
    SemanticReviewError,
    SemanticReviewRequest,
    SemanticReviewView,
)
from fastfence.app.interfaces.http.semantic_suite_store import (
    SemanticSuiteStore,
)
from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.domain.models import Identity, Policy, Snapshot

REVIEW_DEADLINE_SECONDS = 120
RECEIPT_TTL_SECONDS = 600
MAX_RECEIPTS = 16


class SemanticReviewSession:
    def __init__(
        self, runtime: ControlRuntime, store: SemanticSuiteStore
    ) -> None:
        self.runtime, self.store = runtime, store
        self._lock = threading.RLock()
        self._busy = False
        self._receipts: dict[str, SemanticReceipt] = {}

    @asynccontextmanager
    async def evaluation_slot(self) -> AsyncIterator[None]:
        with self._lock:
            if self._busy:
                raise SemanticReviewError("semantic_review_busy", 429)
            self._busy = True
        try:
            async with asyncio.timeout(REVIEW_DEADLINE_SECONDS):
                yield
        finally:
            with self._lock:
                self._busy = False

    async def evaluate_case(
        self, policy: Policy, case: RuleCase
    ) -> SemanticOutcome:
        return await evaluate_case(self.runtime, policy, case)

    def _base(self, version: int) -> Snapshot:
        base = self.runtime.snapshot()
        if base.policy.version != version:
            raise SemanticReviewError("semantic_review_snapshot_changed")
        if not self.runtime.diagnostics().get("management_writable", False):
            raise SemanticReviewError("policy_source_is_read_only")
        return base

    def _unchanged(self, base: Snapshot, digest: str) -> None:
        if self.runtime.snapshot() != base:
            raise SemanticReviewError("semantic_review_snapshot_changed")
        if self.store.read().digest != digest:
            raise SemanticReviewError("semantic_review_suite_changed")

    def _prune(self) -> None:
        now, snapshot = time.monotonic(), self.runtime.snapshot()
        self._receipts = {
            key: receipt
            for key, receipt in self._receipts.items()
            if receipt.expires_monotonic > now and receipt.base == snapshot
        }

    async def _compare(
        self,
        base: Policy,
        candidate: Policy,
        cases: tuple[RuleCase, ...],
        results: list[SemanticCaseResult],
    ) -> None:
        for case in cases:
            before = await self.evaluate_case(base, case)
            results.append(
                SemanticCaseResult(
                    **case.model_dump(),
                    before=before,
                    after=SemanticOutcome(
                        status="not_evaluated", reason="not_reached"
                    ),
                    passed=False,
                )
            )
            after = await self.evaluate_case(candidate, case)
            results[-1] = results[-1].model_copy(
                update={
                    "after": after,
                    "passed": before.status != "error"
                    and after.status == "evaluated"
                    and after.decision == case.expected,
                }
            )

    async def review(
        self, request: SemanticReviewRequest, identity: Identity
    ) -> SemanticReviewView:
        base = self._base(request.base_version)
        candidate = candidate_policy(base.policy, request.rule)
        suite = self.store.read()
        merged = self.store.merge(suite, candidate, request.rule, request.cases)
        results: list[SemanticCaseResult] = []
        deadline_exceeded = False
        try:
            async with self.evaluation_slot():
                with self._lock:
                    self._prune()
                    if len(self._receipts) >= MAX_RECEIPTS:
                        raise SemanticReviewError(
                            "semantic_review_capacity_wait_for_expiry", 429
                        )
                await self._compare(
                    base.policy, candidate, merged.cases, results
                )
        except TimeoutError:
            deadline_exceeded = True
            self._deadline_results(merged.cases, results)
        with self._lock:
            self._unchanged(base, suite.digest)
            passed = (
                bool(results)
                and not deadline_exceeded
                and not merged.missing_rules
                and all(row.passed for row in results)
            )
            receipt = (
                self._receipt(
                    request,
                    identity,
                    base,
                    candidate,
                    merged.cases,
                    suite.digest,
                )
                if passed
                else None
            )
            return SemanticReviewView(
                review_id=receipt.review_id if receipt else None,
                base_version=base.policy.version,
                candidate_version=candidate.version,
                feed_version=base.feed.version,
                expires_at=receipt.expires_at if receipt else None,
                model=candidate.semantic.model,
                yaml_diff=yaml_diff(base.policy, candidate),
                cases=tuple(results),
                tests_passed=passed,
                warnings=merged.warnings
                + (
                    ("semantic_review_deadline_exceeded",)
                    if deadline_exceeded
                    else ()
                ),
                missing_rules=merged.missing_rules,
            )

    @staticmethod
    def _deadline_results(
        cases: tuple[RuleCase, ...], results: list[SemanticCaseResult]
    ) -> None:
        failure = SemanticOutcome(
            status="error", reason="semantic_review_deadline_exceeded"
        )
        if results and results[-1].after.status == "not_evaluated":
            results[-1] = results[-1].model_copy(
                update={"after": failure, "passed": False}
            )
        for case in cases[len(results) :]:
            results.append(
                SemanticCaseResult(
                    **case.model_dump(),
                    before=SemanticOutcome(
                        status="not_evaluated",
                        reason="semantic_review_deadline_exceeded",
                    ),
                    after=failure,
                    passed=False,
                )
            )

    def _receipt(
        self,
        request: SemanticReviewRequest,
        identity: Identity,
        base: Snapshot,
        candidate: Policy,
        cases: tuple[RuleCase, ...],
        digest: str,
    ) -> SemanticReceipt:
        self._prune()
        if len(self._receipts) >= MAX_RECEIPTS:
            raise SemanticReviewError(
                "semantic_review_capacity_wait_for_expiry", 429
            )
        receipt = SemanticReceipt(
            review_id=secrets.token_urlsafe(32),
            subject=identity.subject,
            tenant=identity.tenant,
            base=base,
            candidate=candidate,
            base_digest=policy_digest(base.policy),
            candidate_digest=policy_digest(candidate),
            feed_digest=hashlib.sha256(
                base.feed.model_dump_json().encode()
            ).hexdigest(),
            request=request,
            cases=cases,
            suite_digest=digest,
            expires_monotonic=time.monotonic() + RECEIPT_TTL_SECONDS,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=RECEIPT_TTL_SECONDS),
        )
        self._receipts[receipt.review_id] = receipt
        return receipt

    def activate(
        self, request: SemanticActivateRequest, identity: Identity
    ) -> dict[str, Any]:
        with self._lock:
            receipt = self._receipts.get(request.review_id)
            if receipt is None or (receipt.subject, receipt.tenant) != (
                identity.subject,
                identity.tenant,
            ):
                raise SemanticReviewError("semantic_review_not_found", 404)
            if receipt.expires_monotonic <= time.monotonic():
                del self._receipts[request.review_id]
                raise SemanticReviewError("semantic_review_expired", 410)
            if request.base_version != receipt.base.policy.version:
                raise SemanticReviewError("semantic_review_snapshot_changed")
            self._unchanged(receipt.base, receipt.suite_digest)
            suite = self.store.read()
            if suite.digest != receipt.suite_digest:
                raise SemanticReviewError("semantic_review_suite_changed")
            prepared = self.store.prepare(
                suite,
                receipt.candidate,
                receipt.request.rule,
                receipt.request.cases,
            )
            self._unchanged(receipt.base, receipt.suite_digest)
            try:
                snapshot = self.runtime.save_policy(
                    receipt.candidate,
                    identity,
                    expected_base_policy=receipt.base.policy,
                    expected_feed_version=receipt.base.feed.version,
                )
            except Exception:
                raise SemanticReviewError(
                    "semantic_review_activation_conflict"
                ) from None
            del self._receipts[request.review_id]
            saved = True
            try:
                self.store.commit(prepared)
            except Exception:
                saved = False
            return {
                "review_id": request.review_id,
                "policy_version": snapshot.policy.version,
                "feed_version": snapshot.feed.version,
                "tests_saved": saved,
                "warnings": [] if saved else ["semantic_tests_not_saved"],
            }
