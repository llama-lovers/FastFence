"""Management-only saved semantic cases and nonactivating real-model replay."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from fastapi import Depends, FastAPI, HTTPException
from pydantic import Field

from fastfence.app.interfaces.http.authoring_regression import policy_digest
from fastfence.app.interfaces.http.semantic_review_models import (
    ReviewModel,
    RuleCase,
    SemanticOutcome,
    SemanticReviewError,
)
from fastfence.app.interfaces.http.semantic_suite_store import (
    SemanticSuiteStore,
    SuiteConflictError,
    SuiteStorageError,
)
from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.semantic_rules import SemanticRule


class SemanticEvaluationPort(Protocol):
    def evaluation_slot(self) -> AbstractAsyncContextManager[None]: ...

    async def evaluate_case(
        self, policy: Policy, case: RuleCase
    ) -> SemanticOutcome: ...


class ReplayRequest(ReviewModel):
    base_version: int = Field(ge=1, strict=True)
    suite_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def saved_suite_view(
    store: SemanticSuiteStore, policy: Policy
) -> dict[str, Any]:
    snapshot = store.read()
    active = {rule.id: rule for rule in policy.semantic.rules}
    digest = policy_digest(policy)
    suites = []
    for suite in snapshot.document.suites:
        status = (
            "not_applicable"
            if suite.rule.id not in active
            else "current"
            if suite.policy_sha256 == digest
            else "policy_changed"
        )
        suites.append({**suite.model_dump(mode="json"), "status": status})
    return {
        "schema_version": 1,
        "suite_digest": snapshot.digest,
        "policy_version": policy.version,
        "suites": suites,
    }


def _tests_passed(results: list[dict[str, Any]]) -> bool:
    return bool(results) and all(row["passed"] for row in results)


async def _case_result(
    session: SemanticEvaluationPort,
    policy: Policy,
    rule: SemanticRule,
    case: RuleCase,
) -> dict[str, Any]:
    if not rule.applies_to(case.direction, case.target):
        outcome = SemanticOutcome(
            status="not_evaluated", reason="scope_changed"
        )
    else:
        outcome = await session.evaluate_case(policy, case)
    return {
        **case.model_dump(mode="json", exclude={"text"}),
        **outcome.model_dump(mode="json"),
        "passed": outcome.status == "evaluated"
        and outcome.decision == case.expected,
    }


def _replay_warnings(
    results: list[dict[str, Any]], skipped: list[dict[str, str]]
) -> list[str]:
    warnings = []
    if skipped:
        warnings.append(
            "Inactive rule suites were not evaluated or counted as passes"
        )
    if not results:
        warnings.append("No saved cases apply to the active policy")
    return warnings


async def replay_saved_suites(
    runtime: ControlRuntime,
    store: SemanticSuiteStore,
    session: SemanticEvaluationPort,
    request: ReplayRequest,
) -> dict[str, Any]:
    async with session.evaluation_slot():
        policy = runtime.snapshot().policy
        if policy.version != request.base_version:
            raise SuiteConflictError("Policy changed; refresh and replay again")
        snapshot = store.read()
        if snapshot.digest != request.suite_digest:
            raise SuiteConflictError(
                "Semantic tests changed; refresh and replay again"
            )
        digest = policy_digest(policy)
        active = {rule.id: rule for rule in policy.semantic.rules}
        results = []
        skipped = []
        warnings = []
        for suite in snapshot.document.suites:
            rule = active.get(suite.rule.id)
            if rule is None:
                skipped.append(
                    {"rule_id": suite.rule.id, "reason": "inactive_rule"}
                )
                continue
            if suite.policy_sha256 != digest:
                warnings.append(
                    f"Rule {rule.id}: replaying cases against changed policy"
                )
            for case in suite.cases:
                results.append(await _case_result(session, policy, rule, case))
        store.assert_unchanged(snapshot.digest)
        if policy_digest(runtime.snapshot().policy) != digest:
            raise SuiteConflictError("Policy changed during replay; run again")
        warnings.extend(_replay_warnings(results, skipped))
        return {
            "policy_version": policy.version,
            "policy_sha256": digest,
            "suite_digest": snapshot.digest,
            "scope": "semantic_only",
            "tests_passed": _tests_passed(results),
            "results": results,
            "skipped": skipped,
            "warnings": warnings,
        }


def configure_semantic_suites(
    app: FastAPI,
    runtime: ControlRuntime,
    admin: Callable[..., Any],
    session: SemanticEvaluationPort,
    store: SemanticSuiteStore,
) -> None:
    @app.get("/api/admin/semantic/tests", dependencies=[Depends(admin)])
    def saved_tests() -> dict[str, Any]:
        try:
            return saved_suite_view(store, runtime.snapshot().policy)
        except SuiteStorageError:
            raise HTTPException(
                409, "Saved semantic tests are invalid or unavailable"
            ) from None

    @app.post("/api/admin/semantic/tests/replay", dependencies=[Depends(admin)])
    async def replay(request: ReplayRequest) -> dict[str, Any]:
        try:
            return await replay_saved_suites(runtime, store, session, request)
        except SuiteConflictError:
            raise HTTPException(
                409,
                "Policy or semantic tests changed; refresh and replay again",
            ) from None
        except SuiteStorageError:
            raise HTTPException(
                409, "Saved semantic tests are invalid or unavailable"
            ) from None
        except SemanticReviewError as error:
            raise HTTPException(error.status, error.reason) from None
        except TimeoutError:
            raise HTTPException(
                503,
                "Semantic replay deadline exceeded; no policy was activated",
            ) from None
