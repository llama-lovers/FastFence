from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from fastfence.modules.anonymization.application.facade import (
    AnonymizationRuntime,
)
from fastfence.modules.anonymization.domain.tokens import parse_token
from fastfence.shared.anonymization import (
    AnonymizationConfig,
    AnonymizationContext,
    AnonymizationError,
    AnonymizationRule,
)


def runtime(**options):
    return AnonymizationRuntime(
        **{
            "keyring": {"test": bytes(range(32))},
            "current_key_id": "test",
            "clock": lambda: 1700000000,
            **options,
        }
    )


def rule(**overrides):
    return AnonymizationRule(
        **{
            "id": "email",
            "operator": "regex",
            "value": r"[A-Za-z]+@example[.]org",
            "replacement": "EMAIL",
            **overrides,
        }
    )


def config(*rules, **overrides):
    return AnonymizationConfig(
        **{
            "enabled": True,
            "rules": rules or (rule(),),
            **overrides,
        }
    )


def context(**overrides):
    return AnonymizationContext(
        **{"tenant": "blue", "subject": "alice", **overrides}
    )


def transform(instance, value, cfg=None, ctx=None, **overrides):
    return instance.transform(
        value,
        context=ctx or context(),
        config=cfg or config(),
        **{"direction": "input", "target": "model", **overrides},
    )


def test_distinct_stable_irreversible_identifiers_without_previous_requests():
    first = transform(
        runtime(), "anna@example.org bob@example.org anna@example.org"
    )
    tokens = first.value.split()
    assert tokens[0] == tokens[2] and tokens[0] != tokens[1]
    assert first.changed and first.findings == ["email"]
    assert transform(runtime(), "anna@example.org").value == tokens[0]
    assert parse_token(tokens[0]).prefix == "EMAIL"
    assert parse_token(tokens[0]).version == "FFI1"
    assert "anna@example.org" not in json.dumps(first.model_dump())
    assert not hasattr(first, "conversation_id")


def test_custom_and_default_prefixes_and_literal_unicode_names():
    result = transform(
        runtime(),
        "Łukasz Zoë Łukasz",
        config(
            rule(
                id="name",
                operator="literal",
                value="Łukasz",
                replacement="ANONIM",
            ),
            rule(
                id="other",
                operator="literal",
                value="Zoë",
                replacement="PERSON",
            ),
        ),
    )
    tokens = result.value.split()
    assert tokens[0] == tokens[2]
    assert [parse_token(token).prefix for token in tokens] == [
        "ANONIM",
        "PERSON",
        "ANONIM",
    ]


def test_nested_values_preserve_keys_and_non_string_types():
    original = {
        "anna@example.org": [
            "anna@example.org",
            {"number": 3, "value": "bob@example.org"},
        ],
        "tuple": (False, None),
    }
    result = transform(runtime(), original)
    assert set(result.value) == set(original)
    assert result.value["tuple"] == (False, None)
    assert result.value["anna@example.org"][1]["number"] == 3
    assert original["anna@example.org"][0] == "anna@example.org"
    assert parse_token(result.value["anna@example.org"][0]).prefix == "EMAIL"


def test_non_cascading_leftmost_longest_and_policy_order():
    cfg = config(
        rule(id="short", operator="literal", value="Ann", replacement="SHORT"),
        rule(id="long", operator="literal", value="Anna", replacement="LONG"),
        rule(id="tie", operator="literal", value="Anna", replacement="TIE"),
        rule(
            id="alias", operator="literal", value="LONG", replacement="CASCADE"
        ),
    )
    result = transform(runtime(), "Anna Ann", cfg)
    assert [parse_token(token).prefix for token in result.value.split()] == [
        "LONG",
        "SHORT",
    ]
    assert result.findings == ["long", "short"]


def test_verified_tokens_are_preserved_without_hiding_adjacent_raw_values():
    instance = runtime()
    cfg = config(rule(id="broad", value="[a-zA-Z_0-9@. ]+"))
    first = transform(instance, "anna@example.org", cfg)
    second = transform(instance, first.value + " bob@example.org", cfg)
    assert second.value.startswith(first.value)
    assert "bob@example.org" not in second.value
    assert second.findings == ["broad"]
    assert not transform(instance, first.value, cfg).changed


def test_reversible_originals_recover_after_restart_and_close_is_stateless():
    cfg = config(rule(allow_restore=True), mode="reversible")
    first = transform(runtime(), "anna@example.org anna@example.org", cfg)
    assert first.value.split()[0] == first.value.split()[1]
    fresh = runtime()
    fresh.close()
    restored = fresh.restore(first.value, context=context(), config=cfg)
    assert restored.value == "anna@example.org anna@example.org"
    assert restored.changed and restored.findings == ["email"]
    assert not hasattr(fresh, "_store")


def test_restore_permission_and_internal_checks_have_distinct_authority():
    instance = runtime()
    denied = config(rule(allow_restore=False), mode="reversible")
    permitted = config(rule(allow_restore=True), mode="reversible")
    protected = transform(instance, "anna@example.org", denied).value
    assert (
        instance.reveal_for_checks(
            protected, context=context(), config=denied, target="model"
        ).value
        == "anna@example.org"
    )
    with pytest.raises(AnonymizationError, match="restore_denied"):
        instance.restore(protected, context=context(), config=denied)
    assert (
        instance.restore(protected, context=context(), config=permitted).value
        == "anna@example.org"
    )


def test_irreversible_policy_cannot_be_upgraded_by_restore_request():
    instance = runtime()
    cfg = config(rule(allow_restore=True))
    protected = transform(instance, "anna@example.org", cfg).value
    with pytest.raises(AnonymizationError, match="restore_denied"):
        instance.restore(protected, context=context(), config=cfg)
    with pytest.raises(AnonymizationError, match="restore_denied"):
        instance.restore(
            protected,
            context=context(),
            config=config(rule(allow_restore=True), mode="reversible"),
        )
    assert (
        instance.reveal_for_checks(
            protected, context=context(), config=cfg, target="model"
        ).value
        == protected
    )


def test_restore_target_is_enforced_even_for_input_only_rule():
    instance = runtime()
    cfg = config(
        rule(target="model", direction="input", allow_restore=True),
        mode="reversible",
    )
    protected = transform(instance, "anna@example.org", cfg).value
    assert (
        instance.restore(
            protected, context=context(), config=cfg, target="model"
        ).value
        == "anna@example.org"
    )
    with pytest.raises(AnonymizationError, match="invalid_token"):
        instance.restore(
            protected, context=context(), config=cfg, target="tool"
        )
    assert (
        transform(instance, "anna@example.org", cfg, target="tool").value
        == "anna@example.org"
    )


def test_config_roundtrip_equality_and_unchecked_copy_revalidation():
    original = config(rule())
    restored = AnonymizationConfig.model_validate(
        original.model_dump(mode="json")
    )
    assert restored == original
    assert hash(restored.rules[0]) == hash(original.rules[0])
    with pytest.raises(TypeError):
        original.rules[0]._compiled = None
    with pytest.raises(TypeError):
        del original.rules[0]._fingerprint
    copied = original.rules[0].model_copy(update={"value": "(?=bad)"})
    with pytest.raises(ValidationError):
        AnonymizationConfig(rules=(copied,))


@pytest.mark.parametrize(
    "pattern", ["", " ", "a*", "(?:a)?", r"\b", "(?=secret)", r"(a)\1"]
)
def test_regex_rejects_blank_empty_matches_and_unsupported_syntax(pattern):
    with pytest.raises(ValidationError):
        rule(value=pattern)


@pytest.mark.parametrize(
    "field", ["enabled", "allow_restore", "case_sensitive"]
)
def test_security_flags_reject_string_booleans(field):
    with pytest.raises(ValidationError):
        if field == "enabled":
            AnonymizationConfig(enabled="true")
        else:
            rule(**{field: "true"})


def test_conversation_fields_are_rejected_and_plain_aliases_are_never_guessed():
    with pytest.raises(ValidationError):
        AnonymizationContext(
            tenant="blue", subject="alice", conversation_id="not-supported"
        )
    result = runtime().restore(
        "[EMAIL_1]",
        context=context(),
        config=config(rule(allow_restore=True), mode="reversible"),
    )
    assert result.value == "[EMAIL_1]" and not result.changed
