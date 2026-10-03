import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastfence.app.interfaces.http.authoring_process import PolicyAuthoringError
from fastfence.app.interfaces.http.authoring_records import (
    ActivationView,
    DraftRequest,
    PolicyAuthorPort,
    PreviewRequest,
    PreviewView,
    ProposalView,
    StoredProposal,
    WorkerResponse,
)
from fastfence.app.interfaces.http.authoring_regression import (
    SavedRegressionSuite,
    policy_digest,
    save_reviewed_tests,
    yaml_diff,
)
from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.application.use_cases.policy_preview import (
    RegressionResult,
    compare_sample,
)
from fastfence.modules.control.domain.models import Identity, Snapshot
from fastfence.modules.control.domain.policy_authoring import (
    DraftEnvelope,
    authoring_catalog,
    prepare_policy,
)


class PolicyAuthoringSession:
    def __init__(
        self,
        runtime: ControlRuntime,
        author: PolicyAuthorPort,
        *,
        ttl: float = 600,
        limit: int = 32,
        tests_path: Path | None = None,
    ) -> None:
        self.runtime, self.author = runtime, author
        self.ttl, self.limit = ttl, limit
        self.tests_path = tests_path
        self._lock = threading.RLock()
        self._proposals: dict[str, StoredProposal] = {}

    def _base(self, version: int) -> Snapshot:
        snapshot = self.runtime.snapshot()
        if snapshot.policy.version != version:
            raise PolicyAuthoringError("policy_base_version_conflict", 409)
        if not self.runtime.diagnostics().get("management_writable", False):
            raise PolicyAuthoringError("policy_source_is_read_only", 409)
        return snapshot

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, value in self._proposals.items()
            if value.expires_monotonic <= now or value.consumed
        ]
        for key in expired:
            del self._proposals[key]

    def _get(self, proposal_id: str, identity: Identity) -> StoredProposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.subject != identity.subject:
            raise PolicyAuthoringError("proposal_not_found", 404)
        if proposal.consumed:
            raise PolicyAuthoringError("proposal_already_activated", 409)
        if proposal.expires_monotonic <= time.monotonic():
            del self._proposals[proposal_id]
            raise PolicyAuthoringError("proposal_expired_redraft", 410)
        self._base(proposal.base_version)
        return proposal

    async def draft(
        self, request: DraftRequest, identity: Identity
    ) -> ProposalView:
        snapshot = self._base(request.base_version)
        with self._lock:
            self._prune()
            if len(self._proposals) >= self.limit:
                raise PolicyAuthoringError(
                    "proposal_capacity_wait_for_expiry", 429
                )
        try:
            response = await self.author.draft(
                {
                    "instruction": request.instruction,
                    "schema": DraftEnvelope.model_json_schema(),
                    "catalog": authoring_catalog(snapshot.policy),
                }
            )
        except PolicyAuthoringError:
            raise
        except Exception:
            raise PolicyAuthoringError("laya_authoring_failed", 503) from None
        try:
            worker = WorkerResponse.model_validate(response)
            envelope = DraftEnvelope.model_validate(worker.proposal)
            if not envelope.supported:
                raise PolicyAuthoringError(
                    "unsupported_or_ambiguous_instruction"
                )
            prepared = prepare_policy(snapshot.policy, envelope)
        except ValueError:
            raise PolicyAuthoringError(
                "invalid_or_unsafe_model_proposal"
            ) from None
        with self._lock:
            self._base(request.base_version)
            self._prune()
            if len(self._proposals) >= self.limit:
                raise PolicyAuthoringError(
                    "proposal_capacity_wait_for_expiry", 429
                )
            proposal = StoredProposal(
                proposal_id=secrets.token_urlsafe(24),
                subject=identity.subject,
                base_version=request.base_version,
                base_policy=snapshot.policy,
                expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl),
                expires_monotonic=time.monotonic() + self.ttl,
                prepared=prepared,
                model=worker.model,
                inference_ms=worker.inference_ms,
                yaml_diff=yaml_diff(snapshot.policy, prepared.candidate),
            )
            self._proposals[proposal.proposal_id] = proposal
            return proposal.view()

    def preview(
        self, request: PreviewRequest, identity: Identity
    ) -> PreviewView:
        with self._lock:
            proposal = self._get(request.proposal_id, identity)
            feed = self.runtime.snapshot().feed
            base = Snapshot(policy=proposal.base_policy, feed=feed)
            candidate = Snapshot(policy=proposal.prepared.candidate, feed=feed)
            tests = (
                tuple(request.tests)
                if request.tests is not None
                else proposal.prepared.tests
            )
            if proposal.prepared.tests and not tests:
                raise PolicyAuthoringError("proposal_tests_required")
            comparisons = [
                compare_sample(
                    base,
                    candidate,
                    sample,
                    index,
                    self.runtime.engine.secrets,
                    self.runtime.engine.anonymization,
                )
                for index, sample in enumerate(request.samples)
            ]
            regressions = []
            for index, test in enumerate(tests):
                comparison = compare_sample(
                    base,
                    candidate,
                    test,
                    index,
                    self.runtime.engine.secrets,
                    self.runtime.engine.anonymization,
                )
                regressions.append(
                    RegressionResult(
                        test=test,
                        comparison=comparison,
                        passed=comparison.after.decision
                        == test.expected_decision,
                    )
                )
            proposal.previewed = True
            proposal.previewed_feed_version = feed.version
            proposal.reviewed_tests = tests
            proposal.tests_passed = all(result.passed for result in regressions)
            return PreviewView(
                **proposal.view().model_dump(),
                results=[pair.after for pair in comparisons],
                comparisons=comparisons,
                test_results=regressions,
                tests_passed=proposal.tests_passed,
                feed_version=feed.version,
            )

    def activate(
        self, proposal_id: str, base_version: int, identity: Identity
    ) -> ActivationView:
        with self._lock:
            proposal = self._get(proposal_id, identity)
            if base_version != proposal.base_version:
                raise PolicyAuthoringError("policy_base_version_conflict", 409)
            if not proposal.previewed:
                raise PolicyAuthoringError("proposal_preview_required", 409)
            if not proposal.tests_passed:
                raise PolicyAuthoringError("proposal_regression_failed", 409)
            if (
                self.runtime.snapshot().feed.version
                != proposal.previewed_feed_version
            ):
                raise PolicyAuthoringError(
                    "proposal_feed_changed_preview_again", 409
                )
            try:
                snapshot = self.runtime.save_policy(
                    proposal.prepared.candidate,
                    identity,
                    expected_feed_version=proposal.previewed_feed_version,
                    expected_base_policy=proposal.base_policy,
                )
            except Exception:
                raise PolicyAuthoringError(
                    "policy_activation_conflict", 409
                ) from None
            proposal.consumed = True
            saved = False
            warnings = []
            if proposal.reviewed_tests:
                try:
                    if self.tests_path is None:
                        raise OSError("No regression path configured")
                    save_reviewed_tests(
                        self.tests_path,
                        SavedRegressionSuite(
                            policy_version=snapshot.policy.version,
                            policy_sha256=policy_digest(snapshot.policy),
                            feed_version=snapshot.feed.version,
                            tests=proposal.reviewed_tests,
                        ),
                    )
                    saved = True
                except OSError:
                    warnings.append("policy_tests_not_saved")
            return ActivationView(
                proposal_id=proposal_id,
                policy_version=snapshot.policy.version,
                operations=list(proposal.prepared.operations),
                tests_saved=saved,
                warnings=warnings,
            )
