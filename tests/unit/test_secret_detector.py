from __future__ import annotations

import builtins
import io
import json
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
import requests
from detect_secrets.plugins.slack import SlackDetector

from fastfence.modules.control.persistence.secrets import OfflineSecrets
from tests.fixtures.secrets import GITHUB_FIXTURE, SLACK_FIXTURE


@pytest.mark.parametrize("secret", [GITHUB_FIXTURE, SLACK_FIXTURE])
def test_additional_secret_formats_are_redacted_with_static_findings(secret):
    detector = OfflineSecrets()
    safe, findings = detector.redact(f"Before {secret} after")
    assert safe.startswith("Before ") and safe.endswith(" after")
    assert secret not in safe
    assert findings and secret not in json.dumps(findings)


def test_nested_keys_lists_and_values_are_inspected_without_mutating_input():
    value = {
        GITHUB_FIXTURE: ["ordinary", {"payload": SLACK_FIXTURE}],
        "untouched": 7,
    }
    safe, findings = OfflineSecrets().redact(value)
    assert findings
    assert GITHUB_FIXTURE not in json.dumps(safe)
    assert SLACK_FIXTURE not in json.dumps(safe)
    assert safe["untouched"] == 7
    assert (
        safe[next(key for key in safe if key != "untouched")][0] == "ordinary"
    )
    assert value[GITHUB_FIXTURE][1]["payload"] == SLACK_FIXTURE


@pytest.mark.parametrize(
    "comment", ["# pragma: allowlist secret", "# pragma: whitelist secret"]
)
def test_untrusted_repository_allowlist_comments_do_not_bypass_scan(comment):
    safe, findings = OfflineSecrets().redact(f"{GITHUB_FIXTURE} {comment}")
    assert findings and GITHUB_FIXTURE not in safe


def test_bounded_scalar_line_wrapping_does_not_hide_secret():
    wrapped = GITHUB_FIXTURE[:22] + "\n" + GITHUB_FIXTURE[22:]
    safe, findings = OfflineSecrets().redact(wrapped)
    assert findings and wrapped not in safe and GITHUB_FIXTURE not in safe


def test_fragments_in_different_fields_are_not_claimed_as_full_credentials():
    value = {"first": GITHUB_FIXTURE[:22], "second": GITHUB_FIXTURE[22:]}
    assert OfflineSecrets().redact(value) == (value, [])


def test_initialized_detector_scans_concurrently_without_io_or_verification(
    monkeypatch,
):
    detector = OfflineSecrets()
    values = [GITHUB_FIXTURE, SLACK_FIXTURE, "ordinary report"] * 8
    expected = [detector.redact(value) for value in values]

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline detector attempted I/O or verification")

    with ThreadPoolExecutor(max_workers=4) as workers:
        # Create worker threads before guarding only the request-time operation.
        list(workers.map(lambda _: None, range(4)))
        with monkeypatch.context() as guarded:
            for owner, name in [
                (builtins, "open"),
                (io, "open"),
                (Path, "open"),
                (Path, "read_text"),
                (socket, "socket"),
                (httpx, "Client"),
                (httpx, "AsyncClient"),
                (requests.Session, "request"),
                (SlackDetector, "verify"),
            ]:
                guarded.setattr(owner, name, forbidden)
            actual = list(workers.map(detector.redact, values))
    assert actual == expected
    assert actual[2] == ("ordinary report", [])
