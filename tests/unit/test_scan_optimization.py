"""Optimization must retain upstream detections and fail-closed decode accounting."""

import base64
from importlib.metadata import version

import pytest
from detect_secrets.plugins.keyword import (
    DENYLIST,
    QUOTES_REQUIRED_DENYLIST_REGEX_TO_GROUP,
    KeywordDetector,
)

from fastfence.modules.control.domain import signature_matching
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import SignatureFeed
from fastfence.modules.control.persistence import secrets
from fastfence.modules.control.persistence.secrets import OfflineSecrets
from tests.fixtures.secrets import GITHUB_FIXTURE


def keyword_cases():
    values = []
    for keyword in DENYLIST:
        names = {keyword.replace("_?", ""), keyword.replace("_?", "_")}
        for name in names:
            for variant in [name, name.upper(), f"my_{name}_suffix"]:
                values.extend(
                    [
                        f'{variant}: "fixture-value"',
                        f'"fixture-value" == {variant}',
                        f'{variant} = "fixture-value"',
                        f'{variant} "fixture-value";',
                        f'{variant} => "fixture-value"',
                    ]
                )
    values.extend(
        [
            'pr\u0131vate_key = "fixture-value"',
            'prİvate_key = "fixture-value"',
            '\u017fervice_key = "fixture-value"',
            'password\n =\n "fixture-value"',
            "password = `fixture-value`",
            "password = 'fixture-value'",
            'approved report "nothing sensitive"',
            'pass word = "fixture-value"',
            "password = unquoted-value",
            "Approved business summary " * 310,
        ]
    )
    return values


def test_keyword_precheck_retains_exact_upstream_candidate_values():
    upstream = KeywordDetector()
    configured = secrets._configure(upstream)
    for text in keyword_cases():
        actual = {
            text[start:end] for start, end in secrets._spans(configured, text)
        }
        assert actual == set(upstream.analyze_string(text)), text


def test_complete_redaction_and_findings_match_unoptimized_detector_configuration():
    optimized, original = OfflineSecrets(), OfflineSecrets()
    original._detectors = tuple(
        secrets._Detector(
            name=detector.name,
            analyze=detector.analyze,
            patterns=detector.patterns,
            whole_value=detector.whole_value,
        )
        for detector in original._detectors
    )
    values = [*keyword_cases(), GITHUB_FIXTURE, 'password = "fixture-\nvalue"']
    values.append({"nested": values[-3:], 'password = "key-fixture"': 4})
    for value in values:
        assert optimized.redact(value) == original.redact(value)


def test_default_keyword_optimization_assumptions_are_explicitly_pinned():
    assert version("detect-secrets") == "1.5.0"
    assert len(QUOTES_REQUIRED_DENYLIST_REGEX_TO_GROUP) == 5
    assert secrets._configure(KeywordDetector()).necessary_pattern is not None


def test_quote_or_keyword_absence_avoids_keyword_scan_but_not_other_plugins(
    monkeypatch,
):
    scans = []
    original = KeywordDetector.analyze_string

    def track(self, text, **kwargs):
        scans.append(text)
        yield from original(self, text, **kwargs)

    monkeypatch.setattr(KeywordDetector, "analyze_string", track)
    detector = OfflineSecrets()
    assert detector.redact("Approved business summary " * 310)[1] == []
    assert detector.redact('Approved "business summary"')[1] == []
    safe, findings = detector.redact(GITHUB_FIXTURE)
    assert GITHUB_FIXTURE not in safe and findings
    assert scans == []
    safe, findings = detector.redact('password = "fixture-value"')
    assert "fixture-value" not in safe
    assert "detect_secrets_KeywordDetector" in findings and scans


def test_unknown_upstream_version_retains_complete_keyword_scan(monkeypatch):
    monkeypatch.setattr(secrets, "version", lambda _: "2.0.0")
    monkeypatch.setattr(
        KeywordDetector,
        "analyze_string",
        lambda self, text: iter(["future-format"]),
    )
    configured = secrets._configure(KeywordDetector())
    assert configured.necessary_pattern is None
    assert list(secrets._spans(configured, "future-format")) == [(0, 13)]


def test_nondefault_keyword_configuration_retains_complete_scan():
    configured = secrets._configure(KeywordDetector(keyword_exclude="public"))
    assert configured.necessary_pattern is None
    assert list(secrets._spans(configured, 'password = "fixture-value"'))
    assert (
        list(secrets._spans(configured, 'public password = "fixture-value"'))
        == []
    )


def capture_decodes(monkeypatch):
    calls = []
    original = signature_matching.base64.b64decode

    def track(value, *args, **kwargs):
        calls.append(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(signature_matching.base64, "b64decode", track)
    return calls


def test_repeated_valid_and_failed_decodes_are_memoized_only_per_inspection(
    monkeypatch,
):
    calls = capture_decodes(monkeypatch)
    encoded = base64.b64encode(b"pickle.loads(").decode()
    text = (encoded + " Approved ") * 10
    views = signature_matching.inspection_views(text)
    assert views.count("pickle.loads(") == 10
    assert len(calls) == 2
    assert signature_matching.inspection_views(text) == views
    assert len(calls) == 4


def test_cache_capacity_falls_back_to_inspection_instead_of_dropping_tail(
    monkeypatch,
):
    monkeypatch.setattr(signature_matching, "MAX_DECODE_CACHE", 1)
    calls = capture_decodes(monkeypatch)
    encoded = base64.b64encode(b"pickle.loads(").decode()
    configured = SignatureFeed.model_validate(
        {
            "version": 1,
            "signatures": [
                {
                    "id": "exploit",
                    "pattern": "pickle.loads(",
                    "description": "test",
                }
            ],
        }
    )
    assert signature_matching.signature_findings(
        "Approved " + (encoded + " ") * 3, configured
    ) == ["exploit"]
    assert len(calls) == 4


def test_repeated_cached_candidates_still_exhaust_existing_candidate_budget(
    monkeypatch,
):
    calls = capture_decodes(monkeypatch)
    encoded = base64.b64encode(b"pickle.loads(").decode()
    with pytest.raises(RejectedError, match="signature_inspection_limit"):
        signature_matching.inspection_views((encoded + " ") * 1025)
    assert len(calls) == 1


def test_repeated_cached_candidates_still_exhaust_decoded_byte_budget(
    monkeypatch,
):
    calls = capture_decodes(monkeypatch)
    encoded = base64.b64encode(b"safe" * 700).decode()
    with pytest.raises(RejectedError, match="signature_inspection_limit"):
        signature_matching.inspection_views((encoded + " ") * 24)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload", [b"eval(data)", b"pickle.loads(\n", b"example > safe?"]
)
def test_memo_preserves_urlsafe_unpadded_printable_decoding(payload):
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    assert signature_matching.inspection_views(encoded) == [
        encoded.casefold(),
        payload.decode().casefold(),
    ]


def test_memo_does_not_make_binary_or_recursive_encodings_inspectable():
    binary = base64.b64encode(b"\xff\x00pickle.loads(").decode()
    assert signature_matching.inspection_views(binary) == [binary.casefold()]
    percent = "%70%69%63%6b%6c%65%2e%6c%6f%61%64%73%28"
    encoded = base64.b64encode(percent.encode()).decode()
    assert signature_matching.inspection_views(encoded) == [
        encoded.casefold(),
        percent,
    ]
