"""Bounded authored literals and word fragments must preserve content semantics."""

import pytest
from pydantic import ValidationError

from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.text_rules import (
    TextRule,
    text_rule_matches,
)


@pytest.mark.parametrize(
    "operator,value,text,expected",
    [
        ("word_contains", "a", "Cat", True),
        ("word_contains", "a", "banana", True),
        ("word_contains", "ab", "xabx", True),
        ("word_contains", "a", "word rhythm", False),
        ("word_contains", "a", "dątą", False),
        ("word_contains", "żół", "ZAŻÓŁĆ", True),
        ("word_contains", "é", "Cafe\u0301", True),
        ("word_contains", "a", "\uff43\uff41\uff54", True),
        ("contains", "a b", "x A B y", True),
        ("contains", ".*", "ordinary content", False),
        ("contains", ".*", "literal .* text", True),
        ("equals", "cat", "cat", True),
        ("equals", "cat", "a cat", False),
        ("equals", "cat", " cat ", False),
    ],
)
def test_literal_operators(operator, value, text, expected):
    rule = TextRule(id="restriction", operator=operator, value=value)
    assert text_rule_matches(rule, text) is expected


def test_case_sensitivity_and_prepared_value_are_not_serialized():
    rule = TextRule(
        id="uppercase",
        operator="word_contains",
        value="  A  ",
        case_sensitive=True,
    )
    assert rule.value == "A"
    assert text_rule_matches(rule, "CAT") and not text_rule_matches(rule, "cat")
    assert set(rule.model_dump()) == {
        "id",
        "operator",
        "value",
        "direction",
        "target",
        "action",
        "case_sensitive",
        "ignore_invisible_characters",
    }
    with pytest.raises(ValidationError):
        rule.value = "changed"


def test_prepared_literal_cannot_change_or_disappear_without_policy_version():
    rule = TextRule(id="word", operator="word_contains", value="CAT")
    original = rule.model_dump(mode="json")
    with pytest.raises(TypeError, match="immutable"):
        rule._normalized_value = "dog"
    with pytest.raises(TypeError, match="immutable"):
        del rule._normalized_value
    assert text_rule_matches(rule, "cat")
    assert not text_rule_matches(rule, "dog")
    assert rule.model_dump(mode="json") == original
    assert original["value"] == "CAT"


def test_revalidation_and_roundtrip_prepare_the_same_readonly_literal():
    rule = TextRule(id="word", operator="word_contains", value="CAT")
    same = TextRule.model_validate(rule)
    restored = TextRule.model_validate_json(rule.model_dump_json())
    for candidate in (same, restored):
        assert candidate.value == "CAT" and text_rule_matches(candidate, "cat")
        assert candidate.model_dump(mode="json") == rule.model_dump(mode="json")
        with pytest.raises(TypeError, match="immutable"):
            candidate._normalized_value = "dog"


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "invalid.id"},
        {"id": "x" * 65},
        {"operator": "regex"},
        {"value": "  \n\t  "},
        {"value": "x" * 129},
        {"operator": "word_contains", "value": "a b"},
        {"operator": "word_contains", "value": "a1"},
        {"operator": "word_contains", "value": "a!"},
        {"operator": "word_contains", "value": "\u0301"},
        {"target": "arbitrary"},
        {"direction": "arbitrary"},
        {"action": "execute"},
        {"regex": "arbitrary generated expression"},
        {"_normalized_value": "attacker replacement"},
    ],
)
def test_invalid_or_executable_rule_forms_are_rejected(changes):
    data = {"id": "restriction", "operator": "contains", "value": "literal"}
    with pytest.raises(ValidationError):
        TextRule.model_validate({**data, **changes})


def test_policy_rejects_duplicate_ids_and_more_than_64_rules(app):
    policy = app.state.runtime.snapshot().policy.editable()
    rule = TextRule(
        id="duplicate", operator="contains", value="literal"
    ).model_dump()
    for rules in [
        [rule, rule],
        [{**rule, "id": f"rule-{i}"} for i in range(65)],
    ]:
        with pytest.raises(ValidationError):
            Policy.model_validate({**policy, "text_rules": rules})


def test_backward_compatible_default_and_maximum_policy_rules(app):
    policy = app.state.runtime.snapshot().policy.editable()
    policy.pop("text_rules", None)
    assert Policy.model_validate(policy).text_rules == ()
    policy["text_rules"] = [
        {"id": f"rule-{i}", "operator": "contains", "value": "literal"}
        for i in range(64)
    ]
    validated = Policy.model_validate(policy)
    assert len(validated.text_rules) == 64
    assert isinstance(validated.model_dump()["text_rules"], list)
