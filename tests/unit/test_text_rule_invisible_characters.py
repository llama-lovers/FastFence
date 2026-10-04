"""Opt-in comparison views cannot rewrite payloads or broaden other semantics."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from fastfence.modules.control.domain.text_rules import (
    TextRule,
    text_rule_findings,
    text_rule_matches,
)


def rule(**overrides):
    return TextRule.model_validate(
        {
            "id": "confidential",
            "operator": "contains",
            "value": "confidential",
            "direction": "both",
            "target": "all",
            **overrides,
        }
    )


@pytest.mark.parametrize("character", list("\u200b\u200c\u200d\u2060\ufeff"))
def test_each_supported_character_is_ignored_only_when_requested(character):
    text = "confi" + character + "dential"
    assert not text_rule_matches(rule(), text)
    assert text_rule_matches(rule(ignore_invisible_characters=True), text)
    literal = rule(value=text)
    assert text_rule_matches(literal, text)
    assert not text_rule_matches(literal, "confidential")
    normalized = rule(value=text, ignore_invisible_characters=True)
    assert text_rule_matches(normalized, "confidential")


@pytest.mark.parametrize("operator", ["contains", "equals", "word_contains"])
def test_operators_use_the_same_opt_in_view(operator):
    configured = rule(operator=operator, ignore_invisible_characters=True)
    assert text_rule_matches(configured, "CONFI\u200bDENTIAL")
    assert text_rule_matches(
        configured,
        "\uff23\uff2f\uff2e\uff26\uff29\u200b\uff24\uff25\uff2e\uff34\uff29\uff21\uff2c",
    )
    assert not text_rule_matches(configured, "confidentiał")
    assert not text_rule_matches(configured, "confi\u034fdential")
    assert not text_rule_matches(configured, "confi\ufe0fdential")
    assert not text_rule_matches(configured, "confi dential")
    assert not text_rule_matches(configured, "confi\ndential")
    if operator == "equals":
        assert not text_rule_matches(configured, " confidential ")
    assert not text_rule_matches(
        rule(ignore_invisible_characters=True, case_sensitive=True),
        "CONFI\u200bDENTIAL",
    )


@pytest.mark.parametrize("value", ["\u200b", "\u200b \ufeff", "\u2060\u200d"])
def test_empty_normalized_values_cannot_be_activated(value):
    with pytest.raises(ValidationError):
        rule(value=value, ignore_invisible_characters=True)


@pytest.mark.parametrize("invalid", ["true", "false", 1, 0, None])
def test_normalization_option_requires_a_real_boolean(invalid):
    with pytest.raises(ValidationError):
        rule(ignore_invisible_characters=invalid)


@pytest.mark.parametrize("direction", ["input", "output"])
@pytest.mark.parametrize("target", ["model", "tool"])
def test_direction_and_target_scoped_views_leave_the_payload_intact(
    direction, target
):
    text = "confi\u200bdential"
    payload = (
        {"prompt": text, "messages": [{"role": "user", "content": text}]}
        if target == "model" and direction == "input"
        else {"text": text}
        if target == "model"
        else {"nested": [text]}
    )
    original = deepcopy(payload)
    configured = rule(
        direction=direction, target=target, ignore_invisible_characters=True
    )
    assert text_rule_findings((configured,), payload, direction, target) == [
        "confidential"
    ]
    other_direction = "output" if direction == "input" else "input"
    other_target = "tool" if target == "model" else "model"
    assert not text_rule_findings(
        (configured,), payload, other_direction, target
    )
    assert not text_rule_findings(
        (configured,), payload, direction, other_target
    )
    assert payload == original


def test_mixed_rules_prepare_at_most_four_views_per_scalar(monkeypatch):
    import fastfence.modules.control.domain.text_rules as matcher

    rules = tuple(
        rule(
            id=f"rule-{index}",
            ignore_invisible_characters=bool(index % 2),
            case_sensitive=bool(index % 4 // 2),
        )
        for index in range(64)
    )
    normalizer = matcher.normalized
    calls = []

    def counted(*args):
        calls.append(args)
        return normalizer(*args)

    monkeypatch.setattr(matcher, "normalized", counted)
    findings = text_rule_findings(
        rules, {"prompt": "confi\u200bdential"}, "input", "model"
    )
    assert len(calls) == 4
    assert findings == sorted(f"rule-{index}" for index in range(1, 64, 2))


def test_schema_and_roundtrip_expose_explicit_default():
    configured = rule(ignore_invisible_characters=True)
    assert (
        TextRule.model_validate_json(configured.model_dump_json()) == configured
    )
    assert rule().ignore_invisible_characters is False
    assert (
        TextRule.model_json_schema()["properties"][
            "ignore_invisible_characters"
        ]["default"]
        is False
    )
