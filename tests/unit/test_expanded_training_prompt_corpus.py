"""Expanded synthetic fixture integrity and local controls, not LLM accuracy."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from evaluation.prompt_corpus import load_cases
from fastfence.modules.control.domain.controls import PATTERNS, privacy_filter
from fastfence.modules.control.domain.models import ModelCall
from fastfence.modules.control.domain.text_rules import (
    TextRule,
    text_rule_findings,
)

FIXTURES = Path(__file__).resolve().parents[1] / "test_data"
EXPANDED = FIXTURES / "training_prompts_expanded.jsonl"
CASES = load_cases(EXPANDED)
BY_SOURCE = {(case.label, case.source_index): case for case in CASES}


def test_expanded_balanced_corpus_preserves_all_original_samples_and_labels():
    assert len(CASES) == 1312
    assert Counter((case.label, case.language) for case in CASES) == {
        (label, language): 328
        for label in ("good_prompt", "bad_prompt")
        for language in ("en", "pl")
    }
    original = load_cases()
    by_id = {case.id: case for case in CASES}
    assert all(by_id[case.id] == case for case in original)
    assert len(set(by_id) - {case.id for case in original}) == 912
    for label in ("good_prompt", "bad_prompt"):
        assert {
            case.source_index for case in CASES if case.label == label
        } == set(range(656))
    for case in CASES:
        assert case.generator == case.labeler == "qwen"
        request = ModelCall.model_validate_json(
            json.dumps(
                {"model": "qwen3:4b", "prompt": case.text}, ensure_ascii=False
            )
        )
        assert request.prompt == case.text
        assert len(case.text.encode()) <= 3043


def test_expanded_manifest_identifies_exact_fixture_separately_from_prior_results():
    manifest = json.loads(
        (FIXTURES / "training_prompts_expanded.manifest.json").read_text()
    )
    assert (
        hashlib.sha256(EXPANDED.read_bytes()).hexdigest()
        == manifest["normalized_sha256"]
    )
    assert EXPANDED.stat().st_size == manifest["normalized_bytes"]
    assert manifest["samples"] == 1312 and manifest["original_overlap"] == 400
    assert manifest["additional_samples"] == 912
    assert (
        manifest["duplicate_ids"]
        == manifest["duplicate_texts"]
        == manifest["conflicting_labels"]
        == 0
    )
    assert all(
        counts
        == {bucket: 164 for bucket in ("short", "medium", "long", "very_long")}
        for counts in manifest["label_length_bucket_counts"].values()
    )


@pytest.mark.parametrize(
    ("label", "index", "matches"),
    [
        ("good_prompt", 212, True),
        ("good_prompt", 216, True),
        ("bad_prompt", 222, True),
        ("bad_prompt", 239, True),
        ("good_prompt", 200, False),
        ("bad_prompt", 200, False),
    ],
)
def test_new_literal_samples_preserve_quote_and_semantic_label_distinction(
    label, index, matches
):
    # Reviewed corpus text includes two benign quoted attacks and two executable
    # overrides. An explicit literal policy deliberately matches all four.
    text = BY_SOURCE[label, index].text
    rule = TextRule(
        id="literal-override",
        operator="contains",
        value="ignore all previous instructions",
        direction="input",
        target="model",
    )
    assert text_rule_findings((rule,), {"prompt": text}, "input", "model") == (
        ["literal-override"] if matches else []
    )
    assert text_rule_findings((rule,), {"text": text}, "output", "model") == []
    assert text_rule_findings((rule,), {"text": text}, "input", "tool") == []


@pytest.mark.parametrize(
    ("label", "index"),
    [
        ("good_prompt", 371),
        ("good_prompt", 519),
        ("bad_prompt", 235),
        ("bad_prompt", 359),
    ],
)
def test_new_email_samples_redact_without_relabelling_prompt_intent(
    label, index
):
    text = BY_SOURCE[label, index].text
    safe, findings = privacy_filter({"prompt": text})
    assert "pii_email" in findings
    assert safe["prompt"] != text and "[REDACTED:pii_email]" in safe["prompt"]
    assert not PATTERNS["pii_email"].search(safe["prompt"])
