from concurrent.futures import ThreadPoolExecutor

import pytest

from fastfence.modules.anonymization.domain.tokens import parse_token
from fastfence.shared.anonymization import (
    AnonymizationConfig,
    AnonymizationError,
)
from tests.unit.test_anonymization import (
    config,
    context,
    rule,
    runtime,
    transform,
)


@pytest.mark.parametrize(
    "owner", [context(tenant="green"), context(subject="bob")]
)
@pytest.mark.parametrize("mode", ["irreversible", "reversible"])
def test_tokens_are_cryptographically_bound_to_trusted_owner(owner, mode):
    cfg = config(rule(allow_restore=True), mode=mode)
    instance = runtime()
    token = transform(instance, "anna@example.org", cfg).value
    with pytest.raises(AnonymizationError, match="invalid_token"):
        transform(instance, token, cfg, owner)
    assert transform(instance, "anna@example.org", cfg, owner).value != token


@pytest.mark.parametrize("index", range(7))
def test_every_reversible_token_component_is_authenticated(index):
    cfg = config(rule(allow_restore=True), mode="reversible")
    instance = runtime()
    token = transform(instance, "anna@example.org", cfg).value
    parts = token[1:-1].split(".")
    value = parts[index]
    parts[index] = (
        "FFR2" if index == 0 else ("B" if value[0] != "B" else "C") + value[1:]
    )
    corrupted = "[" + ".".join(parts) + "]"
    with pytest.raises(AnonymizationError) as error:
        instance.restore(corrupted, context=context(), config=cfg)
    assert "anna@example.org" not in str(error.value)
    assert corrupted not in str(error.value)


def test_expiry_is_enforced_after_restart_without_a_lookup():
    cfg = config(rule(allow_restore=True), mode="reversible")
    token = transform(runtime(ttl_seconds=60), "anna@example.org", cfg).value
    expired = runtime(clock=lambda: 1700000060)
    with pytest.raises(AnonymizationError, match="token_expired"):
        expired.reveal_for_checks(
            token, context=context(), config=cfg, target="model"
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"value": "[a-z]+@example[.]org"},
        {"direction": "input"},
        {"replacement": "PERSON"},
        {"case_sensitive": False},
    ],
)
def test_changed_active_rule_invalidates_tokens(changes):
    instance = runtime()
    token = transform(
        instance, "anna@example.org", config(mode="reversible")
    ).value
    with pytest.raises(AnonymizationError, match="invalid_token"):
        transform(instance, token, config(rule(**changes), mode="reversible"))


def test_disabled_or_removed_rules_cannot_accept_previous_tokens():
    token = transform(
        runtime(), "anna@example.org", config(mode="reversible")
    ).value
    for cfg in (AnonymizationConfig(), AnonymizationConfig(enabled=True)):
        with pytest.raises(AnonymizationError, match="invalid_token"):
            transform(runtime(), token, cfg)


def test_reversible_parallel_calls_have_stable_ids_and_distinct_ciphertexts():
    cfg = config(rule(allow_restore=True), mode="reversible")
    instance = runtime()

    def roundtrip(_):
        token = transform(instance, "anna@example.org", cfg).value
        assert (
            runtime().restore(token, context=context(), config=cfg).value
            == "anna@example.org"
        )
        return token

    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(roundtrip, range(32)))
    assert len(set(tokens)) == 32
    assert len({parse_token(token).identifier for token in tokens}) == 1


def test_key_rotation_accepts_old_keys_until_explicitly_removed():
    cfg = config(rule(allow_restore=True), mode="reversible")
    token = transform(runtime(), "anna@example.org", cfg).value
    rotated = runtime(
        keyring={"test": bytes(range(32)), "next": bytes(range(32, 64))},
        current_key_id="next",
    )
    assert (
        rotated.restore(token, context=context(), config=cfg).value
        == "anna@example.org"
    )
    new = transform(rotated, "anna@example.org", cfg).value
    assert parse_token(new).key_id == "next"
    assert parse_token(new).identifier != parse_token(token).identifier
    revoked = runtime(
        keyring={"next": bytes(range(32, 64))}, current_key_id="next"
    )
    with pytest.raises(AnonymizationError, match="invalid_token"):
        transform(revoked, token, cfg)


@pytest.mark.parametrize(
    "marker", ["[FFR1.bad]", "[FFR1.bad", "[ffr1.bad]", "[FFI2.bad]"]
)
def test_forged_or_incomplete_reserved_markers_fail_closed(marker):
    with pytest.raises(AnonymizationError, match="invalid_token"):
        transform(runtime(), marker)


def test_unicode_value_and_request_replacement_caps_fail_closed():
    cfg = config(rule(operator="literal", value="Łukasz"))
    with pytest.raises(AnonymizationError, match="value_too_large"):
        transform(runtime(max_value_bytes=6), "Łukasz", cfg)
    with pytest.raises(AnonymizationError, match="capacity"):
        transform(
            runtime(max_replacements=1), "anna@example.org bob@example.org"
        )
    with pytest.raises(AnonymizationError, match="token_too_large"):
        transform(
            runtime(max_token_bytes=128),
            "a" * 100 + "@example.org",
            config(mode="reversible"),
        )


def test_reversible_token_is_not_exported_under_irreversible_policy():
    token = transform(
        runtime(), "anna@example.org", config(mode="reversible")
    ).value
    with pytest.raises(AnonymizationError, match="restore_denied"):
        transform(runtime(), token, config())


def test_local_transform_and_restore_do_not_read_files_or_connect(monkeypatch):
    import builtins
    import socket
    from pathlib import Path

    import re2

    cfg = config(rule(allow_restore=True), mode="reversible")
    instance = runtime()

    def forbidden(*args, **kwargs):
        pytest.fail(
            "Stateless request performed configuration I/O or recompiled a rule"
        )

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(re2, "compile", forbidden)
    token = transform(instance, "anna@example.org", cfg).value
    assert (
        instance.restore(token, context=context(), config=cfg).value
        == "anna@example.org"
    )


def test_unicode_prefix_cannot_shift_authenticated_token_offsets():
    cfg = config(rule(allow_restore=True), mode="reversible")
    token = transform(runtime(), "anna@example.org", cfg).value
    assert (
        runtime().restore("İ " + token, context=context(), config=cfg).value
        == "İ anna@example.org"
    )
