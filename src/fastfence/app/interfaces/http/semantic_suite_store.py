"""Fixed-path bounded management storage; never read on the invocation path."""

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError

from fastfence.app.interfaces.http.authoring_regression import policy_digest
from fastfence.app.interfaces.http.semantic_review_models import (
    RuleCase,
    SemanticCase,
    SemanticReviewRequest,
)
from fastfence.app.interfaces.http.semantic_suite_records import (
    MergedSemanticCases,
    PreparedSuiteWrite,
    SavedSemanticSuite,
    SemanticSuiteFile,
    SuiteSnapshot,
)
from fastfence.app.interfaces.http.semantic_suite_yaml import load_suite_yaml
from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.semantic_rules import SemanticRule

MAX_SUITE_BYTES = 65_536


class SuiteStorageError(ValueError):
    pass


class SuiteConflictError(SuiteStorageError):
    pass


def _scope_valid(suite: SavedSemanticSuite, rule: SemanticRule) -> bool:
    try:
        SemanticReviewRequest(
            base_version=suite.policy_version,
            rule=rule,
            cases=tuple(
                SemanticCase.model_validate(
                    case.model_dump(exclude={"rule_id"})
                )
                for case in suite.cases
            ),
        )
    except ValidationError:
        return False
    return True


class SemanticSuiteStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "config/semantic-policy-tests.yaml"

    def _safe_parent(self) -> None:
        if self.path.parent.is_symlink() or not self.path.parent.is_dir():
            raise SuiteStorageError("Semantic test directory unavailable")

    def read(self) -> SuiteSnapshot:
        try:
            self._safe_parent()
            try:
                descriptor = os.open(
                    self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                )
            except FileNotFoundError:
                return SuiteSnapshot(
                    document=SemanticSuiteFile(),
                    digest=hashlib.sha256(b"").hexdigest(),
                )
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                    raise SuiteStorageError(
                        "Semantic test file must be private and regular"
                    )
                raw = stream.read(MAX_SUITE_BYTES + 1)
            if len(raw) > MAX_SUITE_BYTES:
                raise SuiteStorageError("Semantic test file too large")
            document = SemanticSuiteFile.model_validate(load_suite_yaml(raw))
            return SuiteSnapshot(
                document=document, digest=hashlib.sha256(raw).hexdigest()
            )
        except (
            OSError,
            ValueError,
            TypeError,
            RecursionError,
            yaml.YAMLError,
        ) as error:
            if isinstance(error, SuiteStorageError):
                raise
            raise SuiteStorageError(
                "Semantic test file is invalid or unavailable"
            ) from None

    def assert_unchanged(self, expected_digest: str) -> None:
        if self.read().digest != expected_digest:
            raise SuiteConflictError("Semantic tests changed; review again")

    def merge(
        self,
        snapshot: SuiteSnapshot,
        candidate: Policy,
        rule: SemanticRule,
        cases: tuple[SemanticCase, ...],
    ) -> MergedSemanticCases:
        active = {item.id: item for item in candidate.semantic.rules}
        previous = {suite.rule.id: suite for suite in snapshot.document.suites}
        merged = [
            RuleCase(**case.model_dump(), rule_id=rule.id) for case in cases
        ]
        warnings = []
        missing = []
        for rule_id in active:
            if rule_id == rule.id:
                continue
            suite = previous.get(rule_id)
            if suite is None:
                warnings.append(
                    f"Rule {rule_id}: untested_rule (no saved cases)"
                )
            elif not _scope_valid(suite, active[rule_id]):
                missing.append(rule_id)
                warnings.append(
                    f"Rule {rule_id}: saved case scope changed; review this rule first"
                )
            else:
                merged.extend(suite.cases)
        warnings.extend(
            self._inactive_warnings(previous.keys() - active.keys())
        )
        try:
            result = MergedSemanticCases(
                cases=tuple(merged),
                warnings=tuple(sorted(warnings)),
                missing_rules=tuple(sorted(missing)),
            )
            self._check_consistent_cases(result)
            self._check_merged_size(result)
            if not missing:
                self._content(snapshot, candidate, rule, cases)
            return result
        except ValidationError:
            raise SuiteStorageError(
                "Merged semantic cases exceed capacity"
            ) from None

    @staticmethod
    def _inactive_warnings(identifiers: set[str]) -> list[str]:
        return [
            f"Rule {identifier}: not_applicable (inactive rule)"
            for identifier in identifiers
        ]

    @staticmethod
    def _check_consistent_cases(result: MergedSemanticCases) -> None:
        expectations: dict[tuple[str, str, str], str] = {}
        for case in result.cases:
            key = (case.text, case.direction, case.target)
            previous = expectations.setdefault(key, case.expected)
            if previous != case.expected:
                raise SuiteStorageError(
                    "Conflicting expectations for the same semantic case"
                )

    @staticmethod
    def _check_merged_size(result: MergedSemanticCases) -> None:
        serialized = json.dumps(
            [case.model_dump() for case in result.cases], ensure_ascii=False
        ).encode()
        if len(serialized) > MAX_SUITE_BYTES:
            raise SuiteStorageError("Merged semantic cases exceed capacity")

    def _content(
        self,
        snapshot: SuiteSnapshot,
        candidate: Policy,
        rule: SemanticRule,
        cases: tuple[SemanticCase, ...],
    ) -> bytes:
        active = {item.id: item for item in candidate.semantic.rules}
        digest = policy_digest(candidate)
        suites = []
        for suite in snapshot.document.suites:
            if suite.rule.id == rule.id:
                continue
            if suite.rule.id in active:
                suite = SavedSemanticSuite(
                    rule=active[suite.rule.id],
                    policy_version=candidate.version,
                    policy_sha256=digest,
                    model=candidate.semantic.model,
                    threshold=candidate.semantic.threshold,
                    cases=suite.cases,
                )
            suites.append(suite)
        suites.append(
            SavedSemanticSuite(
                rule=rule,
                policy_version=candidate.version,
                policy_sha256=digest,
                model=candidate.semantic.model,
                threshold=candidate.semantic.threshold,
                cases=tuple(
                    RuleCase(**case.model_dump(), rule_id=rule.id)
                    for case in cases
                ),
            )
        )
        document = SemanticSuiteFile(suites=tuple(suites))
        content = yaml.safe_dump(
            document.model_dump(mode="json"), sort_keys=False
        ).encode()
        if len(content) > MAX_SUITE_BYTES:
            raise SuiteStorageError("Saved semantic tests exceed capacity")
        return content

    def _temporary(self, content: bytes) -> Path:
        self._safe_parent()
        descriptor, filename = tempfile.mkstemp(
            prefix=".semantic-tests-", dir=self.path.parent
        )
        path = Path(filename)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def prepare(
        self,
        snapshot: SuiteSnapshot,
        candidate: Policy,
        rule: SemanticRule,
        cases: tuple[SemanticCase, ...],
    ) -> PreparedSuiteWrite:
        try:
            self.assert_unchanged(snapshot.digest)
            content = self._content(snapshot, candidate, rule, cases)
            temporary = self._temporary(content)
            temporary.unlink()
            return PreparedSuiteWrite(
                content=content, expected_digest=snapshot.digest
            )
        except (OSError, ValidationError):
            raise SuiteStorageError("Semantic tests cannot be saved") from None

    def commit(self, prepared: PreparedSuiteWrite) -> None:
        temporary = None
        try:
            temporary = self._temporary(prepared.content)
            self.assert_unchanged(prepared.expected_digest)
            os.replace(temporary, self.path)
        except OSError:
            raise SuiteStorageError(
                "Semantic tests could not be saved"
            ) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
