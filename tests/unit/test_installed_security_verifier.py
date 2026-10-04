"""The installed security harness stages existing tests and sanitizes evidence."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import installed_security_probe as probe
from scripts import verify_installed_security as verifier

ROOT = Path(__file__).resolve().parents[2]


def test_staged_suite_is_exact_source_without_product_or_private_state(
    tmp_path,
):
    checksums = verifier.stage(ROOT, tmp_path)
    assert set(checksums) == set(verifier.TEST_FILES + verifier.FIXTURES)
    for name, digest in checksums.items():
        assert (tmp_path / name).read_bytes() == (ROOT / name).read_bytes()
        assert digest == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "fastfence").exists()
    assert not (tmp_path / "state").exists()
    assert "pythonpath" not in (tmp_path / "pytest.ini").read_text()
    assert "cov" not in (tmp_path / "pytest.ini").read_text()


def test_external_fixture_symlink_is_rejected_before_copy(tmp_path):
    source = tmp_path / "bundle"
    target = source / verifier.TEST_FILES[0]
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("synthetic private content")
    target.symlink_to(outside)
    with pytest.raises(ValueError, match="external"):
        verifier.stage(source, tmp_path / "staged")


def test_evidence_omits_parameter_payload_and_preserves_teardown_failure(
    monkeypatch,
):
    monkeypatch.setattr(probe, "records", {})
    report = SimpleNamespace(
        nodeid="tests/test_synthetic.py::test_case[SYNTHETIC_PRIVATE_PAYLOAD]",
        when="call",
        outcome="passed",
        failed=False,
        skipped=False,
    )
    probe.pytest_runtest_logreport(report)
    report.when, report.outcome, report.failed = "teardown", "failed", True
    probe.pytest_runtest_logreport(report)
    records = list(probe.records.values())
    assert len(records) == 1 and records[0]["outcome"] == "failed"
    assert "SYNTHETIC_PRIVATE_PAYLOAD" not in str(records)
    assert records[0]["test"] == "tests/test_synthetic.py::test_case"


def test_network_guard_prevents_real_connection_and_counts_attempt(monkeypatch):
    monkeypatch.setattr(probe, "network_attempts", 0)
    with pytest.raises(OSError, match="network is disabled"):
        probe.deny_network("https://model.invalid")
    assert probe.network_attempts == 1


@pytest.mark.parametrize("collected", [143, 151])
def test_complete_success_accepts_original_and_expanded_suite(collected):
    report = {
        "collected": collected,
        "exit_code": 0,
        "results": [{}] * collected,
    }
    counts = {"passed": collected, "failed": 0, "skipped": 0}
    assert verifier.complete_success(report, 0, counts)


@pytest.mark.parametrize(
    (
        "collected",
        "recorded",
        "passed",
        "failed",
        "skipped",
        "exit_code",
        "process_code",
    ),
    [
        (0, 0, 0, 0, 0, 0, 0),
        (142, 142, 142, 0, 0, 0, 0),
        (151, 150, 150, 0, 0, 0, 0),
        (151, 151, 150, 0, 1, 0, 0),
        (151, 151, 150, 1, 0, 0, 0),
        (151, 151, 151, 0, 0, 1, 0),
        (151, 151, 151, 0, 0, 0, 1),
        (151, 152, 151, 0, 0, 0, 0),
        (151, 151, 152, 0, 0, 0, 0),
    ],
)
def test_complete_success_rejects_incomplete_or_failed_evidence(
    collected, recorded, passed, failed, skipped, exit_code, process_code
):
    report = {
        "collected": collected,
        "exit_code": exit_code,
        "results": [{}] * recorded,
    }
    counts = {"passed": passed, "failed": failed, "skipped": skipped}
    assert not verifier.complete_success(report, process_code, counts)
