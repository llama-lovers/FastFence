"""Private suite boundaries, preservation and explicit two-file failure handling."""

import os

import pytest
from pydantic import ValidationError

from fastfence.app.interfaces.http.semantic_suite_store import (
    MAX_SUITE_BYTES,
    SemanticSuiteStore,
    SuiteConflictError,
    SuiteStorageError,
)
from tests.fixtures.semantic_suites import suite_cases, suite_policy, suite_rule


@pytest.fixture
def store(project):
    return SemanticSuiteStore(project)


def save(store, policy, rule=None, cases=None):
    store.commit(
        store.prepare(
            store.read(), policy, rule or suite_rule(), cases or suite_cases()
        )
    )


def private_write(path, content):
    path.write_bytes(content)
    path.chmod(0o600)


def test_missing_store_and_private_roundtrip(store, app):
    original = store.read()
    assert original.document.suites == ()
    rule = suite_rule()
    policy = suite_policy(app.state.runtime.snapshot().policy, rule)
    prepared = store.prepare(original, policy, rule, suite_cases())
    assert not store.path.exists()
    assert not list(store.path.parent.glob(".semantic-tests-*"))
    store.commit(prepared)
    result = store.read()
    assert result.digest != original.digest
    assert os.stat(store.path).st_mode & 0o777 == 0o600
    assert result.document.suites[0].cases[0].text == suite_cases()[0].text
    with pytest.raises(ValidationError):
        result.document.suites[0].cases[0].text = "replacement"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"{",
        b"schema_version: 1\nschema_version: 1\nsuites: []\n",
        b"schema_version: 1\nsuites: &cases [*cases]\n",
        b"!!python/object/apply:os.system ['echo forbidden']",
        b"schema_version: 2\nsuites: []\n",
        b"\xff",
        b"[" * 40 + b"]" * 40,
    ],
)
def test_malformed_files_fail_with_static_error(store, content):
    private_write(store.path, content)
    with pytest.raises(SuiteStorageError):
        store.read()


def test_read_bound_is_bytes_and_accepts_exact_limit(store):
    valid = b"schema_version: 1\nsuites: []\n"
    private_write(store.path, valid + b" " * (MAX_SUITE_BYTES - len(valid)))
    assert store.read().document.suites == ()
    with store.path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(SuiteStorageError, match="too large"):
        store.read()


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo", "public"])
def test_unsafe_files_are_rejected_without_following_or_blocking(
    store, tmp_path, kind
):
    if kind == "symlink":
        target = tmp_path / "original"
        target.write_text("private original")
        store.path.symlink_to(target)
    elif kind == "directory":
        store.path.mkdir()
    elif kind == "fifo":
        os.mkfifo(store.path, 0o600)
    else:
        store.path.write_text("schema_version: 1\nsuites: []\n")
        store.path.chmod(0o644)
    with pytest.raises(SuiteStorageError):
        store.read()
    if kind == "symlink":
        assert target.read_text() == "private original"


def test_conflict_preserves_external_edits_and_cleans_temporary(store, app):
    policy = suite_policy(app.state.runtime.snapshot().policy, suite_rule())
    save(store, policy)
    prepared = store.prepare(store.read(), policy, suite_rule(), suite_cases())
    external = store.path.read_bytes() + b"\n# edited externally\n"
    private_write(store.path, external)
    with pytest.raises(SuiteConflictError):
        store.commit(prepared)
    assert store.path.read_bytes() == external
    assert not list(store.path.parent.glob(".semantic-tests-*"))


def test_commit_rechecks_digest_after_temporary_write(store, app, monkeypatch):
    policy = suite_policy(app.state.runtime.snapshot().policy, suite_rule())
    save(store, policy)
    prepared = store.prepare(store.read(), policy, suite_rule(), suite_cases())
    original = store._temporary
    external = store.path.read_bytes() + b"\n# concurrent update\n"

    def changed(content):
        temporary = original(content)
        private_write(store.path, external)
        return temporary

    monkeypatch.setattr(store, "_temporary", changed)
    with pytest.raises(SuiteConflictError):
        store.commit(prepared)
    assert store.path.read_bytes() == external


def test_replace_failure_preserves_original_and_cleans_temp(
    store, app, monkeypatch
):
    policy = suite_policy(app.state.runtime.snapshot().policy, suite_rule())
    save(store, policy)
    before = store.path.read_bytes()
    prepared = store.prepare(store.read(), policy, suite_rule(), suite_cases())

    def fail(*_):
        raise OSError("PRIVATE_PATH_DIAGNOSTIC")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(SuiteStorageError, match="could not be saved") as error:
        store.commit(prepared)
    assert "PRIVATE_PATH" not in str(error.value)
    assert store.path.read_bytes() == before
    assert not list(store.path.parent.glob(".semantic-tests-*"))


def test_unwritable_preflight_fails_before_any_policy_publication(
    store, app, monkeypatch
):
    policy = suite_policy(app.state.runtime.snapshot().policy, suite_rule())

    def fail(*_):
        raise PermissionError("private path")

    monkeypatch.setattr(store, "_temporary", fail)
    with pytest.raises(SuiteStorageError, match="cannot be saved"):
        store.prepare(store.read(), policy, suite_rule(), suite_cases())
    assert not store.path.exists()
    assert app.state.runtime.snapshot().policy.version == 1


def test_merge_preserves_other_active_cases_and_identifies_inactive(store, app):
    first, second = suite_rule("first"), suite_rule("second")
    policy = suite_policy(app.state.runtime.snapshot().policy, first)
    save(store, policy, first)
    candidate = suite_policy(policy, first, second)
    merged = store.merge(store.read(), candidate, second, suite_cases())
    assert [case.rule_id for case in merged.cases] == [
        "second",
        "second",
        "first",
        "first",
    ]
    assert merged.missing_rules == ()
    save(store, candidate, second)
    snapshot = store.read()
    assert snapshot.document.suites[0].cases == tuple(
        c for c in merged.cases if c.rule_id == "first"
    )
    removed = suite_policy(candidate, second)
    merged = store.merge(snapshot, removed, second, suite_cases())
    assert len(merged.cases) == 2
    assert any(
        "first: not_applicable" in warning for warning in merged.warnings
    )


def test_missing_other_rule_suite_is_explicit(store, app):
    first, second = suite_rule("first"), suite_rule("second")
    candidate = suite_policy(app.state.runtime.snapshot().policy, first, second)
    merged = store.merge(store.read(), candidate, second, suite_cases())
    assert merged.missing_rules == ()
    assert any("first: untested_rule" in warning for warning in merged.warnings)


def test_serialized_capacity_rejected_before_save(store, app):
    cases = tuple(
        suite_cases()[index % 2].model_copy(
            update={"id": f"case-{index}", "text": str(index) + "x" * 4090}
        )
        for index in range(16)
    )
    policy = suite_policy(app.state.runtime.snapshot().policy, suite_rule())
    with pytest.raises(SuiteStorageError, match="capacity"):
        store.prepare(store.read(), policy, suite_rule(), cases)
    assert not store.path.exists()


def test_expanded_saved_scope_requires_reviewing_that_rule_first(store, app):
    first, second = suite_rule("first"), suite_rule("second")
    policy = suite_policy(app.state.runtime.snapshot().policy, first)
    save(store, policy, first)
    expanded = first.model_copy(update={"direction": "both"})
    candidate = suite_policy(policy, expanded, second)
    merged = store.merge(store.read(), candidate, second, suite_cases())
    assert merged.missing_rules == ("first",)
    assert any("scope changed" in warning for warning in merged.warnings)


def test_merge_rejects_oversized_serialization_before_inference(store, app):
    cases = tuple(
        suite_cases()[index % 2].model_copy(
            update={"id": f"case-{index}", "text": str(index) + "x" * 4090}
        )
        for index in range(16)
    )
    policy = suite_policy(app.state.runtime.snapshot().policy, suite_rule())
    with pytest.raises(SuiteStorageError, match="capacity"):
        store.merge(store.read(), policy, suite_rule(), cases)
    assert not store.path.exists()


def test_more_than_64_stored_cases_are_rejected_on_read(store, app):
    import yaml

    policy = suite_policy(app.state.runtime.snapshot().policy, suite_rule())
    save(store, policy)
    document = store.read().document.model_dump(mode="json")
    original = document["suites"][0]
    suites = []
    for index in range(33):
        identifier = f"rule-{index}"
        suites.append(
            {
                **original,
                "rule": {**original["rule"], "id": identifier},
                "cases": [
                    {**case, "rule_id": identifier}
                    for case in original["cases"]
                ],
            }
        )
    content = yaml.safe_dump({"schema_version": 1, "suites": suites}).encode()
    assert len(content) < MAX_SUITE_BYTES
    private_write(store.path, content)
    with pytest.raises(SuiteStorageError, match="invalid"):
        store.read()
