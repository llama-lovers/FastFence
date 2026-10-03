"""Corpus integrity and actual deterministic contracts, not mocked AI accuracy."""

import json
from collections import Counter

import pytest
from pydantic import ValidationError

from evaluation.prompt_corpus import (
    MAX_CORPUS_BYTES,
    classification_summary,
    load_cases,
)
from fastfence.modules.control.domain.controls import PATTERNS, privacy_filter
from fastfence.modules.control.domain.models import ModelCall
from fastfence.modules.control.domain.text_rules import (
    TextRule,
    text_rule_findings,
)

CASES = load_cases()
BY_SOURCE = {(case.label, case.source_index): case for case in CASES}


def test_corpus_is_balanced_bilingual_unique_and_valid_model_input():
    assert len(CASES) == 400
    assert Counter((case.label, case.language) for case in CASES) == {
        (label, language): 100
        for label in ("good_prompt", "bad_prompt")
        for language in ("en", "pl")
    }
    for label in ("good_prompt", "bad_prompt"):
        assert {
            case.source_index for case in CASES if case.label == label
        } == set(range(200))
    for case in CASES:
        assert case.generator == case.labeler == "qwen"
        request = ModelCall.model_validate_json(
            json.dumps(
                {"model": "qwen3:0.6b", "prompt": case.text}, ensure_ascii=False
            )
        )
        assert request.prompt == case.text
        assert len(case.text.encode("utf-8")) < 16384


@pytest.mark.parametrize(
    ("label", "index", "literal_match"),
    [
        ("bad_prompt", 2, True),
        ("bad_prompt", 19, True),
        ("bad_prompt", 61, True),
        ("good_prompt", 37, True),
        ("good_prompt", 48, True),
        ("good_prompt", 0, False),
        ("good_prompt", 5, False),
        ("good_prompt", 9, False),
        ("bad_prompt", 0, False),
        ("bad_prompt", 1, False),
    ],
)
def test_explicit_literal_policy_is_not_a_semantic_label_or_quote_detector(
    label, index, literal_match
):
    # These ten expectations were reviewed against the original text. Quoted
    # matches still violate an explicit contains policy; other attacks need AI.
    case = BY_SOURCE[label, index]
    rule = TextRule(
        id="literal-override",
        operator="contains",
        value="ignore all previous instructions",
        direction="input",
        target="model",
    )
    assert text_rule_findings(
        (rule,), {"prompt": case.text}, "input", "model"
    ) == (["literal-override"] if literal_match else [])
    assert (
        text_rule_findings((rule,), {"text": case.text}, "output", "model")
        == []
    )
    assert (
        text_rule_findings((rule,), {"query": case.text}, "input", "tool") == []
    )
    assert (
        text_rule_findings(
            (rule,), {"model": case.text, "prompt": "Hi"}, "input", "model"
        )
        == []
    )


@pytest.mark.parametrize(
    ("label", "index"),
    [
        ("good_prompt", 14),
        ("good_prompt", 70),
        ("good_prompt", 168),
        ("bad_prompt", 108),
        ("bad_prompt", 128),
        ("bad_prompt", 151),
    ],
)
def test_real_synthetic_addresses_are_redacted_independently_of_injection_label(
    label, index
):
    text = BY_SOURCE[label, index].text
    safe, findings = privacy_filter({"messages": [{"content": text}]})
    assert findings == ["pii_email"]
    redacted = safe["messages"][0]["content"]
    assert redacted != text and "[REDACTED:pii_email]" in redacted
    assert not PATTERNS["pii_email"].search(redacted)


@pytest.mark.parametrize(
    "mode",
    [
        "label",
        "text",
        "extra",
        "duplicate_id",
        "duplicate_text",
        "empty",
        "oversized",
    ],
)
def test_ingestion_rejects_corrupt_or_conflicting_data(tmp_path, mode):
    first, second = [case.model_dump() for case in CASES[:2]]
    if mode == "label":
        first["label"] = "unknown"
    elif mode == "text":
        first["text"] = 123
    elif mode == "extra":
        first["expected_score"] = 1
    elif mode == "duplicate_id":
        second["id"] = first["id"]
    elif mode == "duplicate_text":
        second["text"] = first["text"]
        second["label"] = "bad_prompt"
    path = tmp_path / "corpus.jsonl"
    content = "\n".join(json.dumps(row) for row in (first, second))
    if mode == "empty":
        content = "\n"
    elif mode == "oversized":
        content = " " * (MAX_CORPUS_BYTES + 1)
    path.write_text(content)
    with pytest.raises((ValueError, ValidationError)):
        load_cases(path)


def test_summary_keeps_errors_out_of_accuracy_without_counting_them_as_success():
    rows = [
        {"expected_blocked": expected, "blocked": observed, "error": None}
        for expected, observed in (
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        )
    ]
    rows.append(
        {"expected_blocked": True, "blocked": None, "error": "unavailable"}
    )
    assert classification_summary(rows) == {
        "samples": 5,
        "errors": 1,
        "true_positives": 1,
        "false_negatives": 1,
        "false_positives": 1,
        "true_negatives": 1,
        "accuracy_on_valid": 0.5,
        "precision": 0.5,
        "recall": 0.5,
    }
    assert classification_summary(rows[-1:])["accuracy_on_valid"] is None
