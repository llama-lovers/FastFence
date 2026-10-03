"""FFR2 recipient encryption, issuer authentication and stateless boundaries."""

import base64
import json
import os
import stat

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from examples.docs.asymmetric_keys import generate_pair
from fastfence.modules.anonymization.domain.tokens import parse_token
from fastfence.modules.anonymization.persistence.asymmetric import (
    AsymmetricEnvelope,
)
from fastfence.shared.anonymization import (
    AnonymizationConfig,
    AnonymizationError,
)
from fastfence.shared.settings.app_settings import AppSettings
from fastfence.workflows.anonymization import build_anonymization
from tests.unit.test_anonymization import (
    config,
    context,
    rule,
    runtime,
    transform,
)


def serialize(private):
    return (
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


@pytest.fixture(scope="module")
def pair():
    return serialize(
        rsa.generate_private_key(public_exponent=65537, key_size=3072)
    )


@pytest.fixture(scope="module")
def other_pair():
    return serialize(
        rsa.generate_private_key(public_exponent=65537, key_size=3072)
    )


def instance(pair, **options):
    return runtime(public_key_pem=pair[0], private_key_pem=pair[1], **options)


def reversible():
    return config(rule(allow_restore=True), mode="reversible")


def test_independent_instances_restore_randomized_tokens_with_stable_scoped_alias(
    pair,
):
    cfg = reversible()
    tokens = [
        transform(instance(pair), "anna@example.org", cfg).value
        for _ in range(3)
    ]
    assert len(set(tokens)) == 3
    assert all(
        token.startswith("[FFR2.") and "anna@example.org" not in token
        for token in tokens
    )
    assert len({parse_token(token).identifier for token in tokens}) == 1
    legacy = transform(runtime(), "anna@example.org", cfg).value
    assert parse_token(legacy).identifier == parse_token(tokens[0]).identifier
    for token in [*tokens, legacy]:
        assert (
            instance(pair).restore(token, context=context(), config=cfg).value
            == "anna@example.org"
        )
    assert (
        transform(instance(pair), "anna@example.org").value
        == transform(runtime(), "anna@example.org").value
    )


@pytest.mark.parametrize("index", range(7))
def test_token_header_and_payload_are_authenticated(pair, index):
    cfg = reversible()
    token = transform(instance(pair), "anna@example.org", cfg).value
    parts = token[1:-1].split(".")
    parts[index] = (
        "FFR1"
        if index == 0
        else ("Z" if parts[index][0] != "Z" else "Y") + parts[index][1:]
    )
    with pytest.raises(AnonymizationError) as caught:
        instance(pair).restore(
            "[" + ".".join(parts) + "]", context=context(), config=cfg
        )
    assert "anna@example.org" not in str(caught.value) and token not in str(
        caught.value
    )


@pytest.mark.parametrize("offset", [0, 31, 32, 415, 416, 427, 428, -1])
def test_envelope_mac_precedes_private_key_decryption(
    pair, monkeypatch, offset
):
    envelope = AsymmetricEnvelope(*pair)
    key = bytes(range(32))
    payload = bytearray(
        envelope.encrypt(b"private-content", b"authenticated-context", key)
    )
    payload[offset] ^= 1

    class ForbiddenDecrypt:
        def decrypt(self, *_args):
            pytest.fail("Unauthenticated envelope reached RSA decryption")

    monkeypatch.setattr(envelope, "_private", ForbiddenDecrypt())
    with pytest.raises(AnonymizationError, match="invalid_token"):
        envelope.decrypt(bytes(payload), b"authenticated-context", key)


@pytest.mark.parametrize(
    "owner", [context(tenant="other"), context(subject="other")]
)
def test_recipient_tokens_remain_bound_to_the_trusted_owner(pair, owner):
    token = transform(instance(pair), "anna@example.org", reversible()).value
    with pytest.raises(AnonymizationError, match="invalid_token"):
        instance(pair).restore(token, context=owner, config=reversible())


def test_changed_rule_expiry_wrong_recipient_and_missing_rsa_fail_closed(
    pair, other_pair
):
    token = transform(instance(pair), "anna@example.org", reversible()).value
    for candidate in [
        runtime(),
        instance(other_pair),
        instance(pair, keyring={"test": b"x" * 32}),
    ]:
        with pytest.raises(AnonymizationError, match="invalid_token"):
            candidate.restore(token, context=context(), config=reversible())
    with pytest.raises(AnonymizationError, match="invalid_token"):
        instance(pair).restore(
            token,
            context=context(),
            config=config(
                rule(value="other", allow_restore=True), mode="reversible"
            ),
        )
    with pytest.raises(AnonymizationError, match="expired"):
        instance(pair, clock=lambda: 1700001800).restore(
            token, context=context(), config=reversible()
        )


def test_restoration_permission_and_irreversible_policy_still_apply(pair):
    token = transform(instance(pair), "anna@example.org", reversible()).value
    with pytest.raises(AnonymizationError, match="restore_denied"):
        instance(pair).restore(
            token, context=context(), config=config(mode="reversible")
        )
    with pytest.raises(AnonymizationError, match="restore_denied"):
        transform(instance(pair), token)


def test_keys_must_be_matching_rsa3072(pair, other_pair):
    weak = serialize(
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    non_rsa = serialize(ed25519.Ed25519PrivateKey.generate())
    for invalid in [
        (pair[0], other_pair[1]),
        weak,
        non_rsa,
        (b"bad", pair[1]),
        (pair[0], b"x" * 16385),
    ]:
        with pytest.raises(ValueError, match="Invalid RSA-3072"):
            AsymmetricEnvelope(*invalid)
    with pytest.raises(ValueError, match="Both"):
        runtime(public_key_pem=pair[0])


def test_fresh_content_key_has_full_value_capacity(pair):
    original = "ą" * 2048
    cfg = config(
        rule(operator="literal", value="ą", allow_restore=True),
        mode="reversible",
    )
    codec = instance(pair)._codec
    token = codec.issue(cfg.rules[0], original, context(), "reversible")
    assert len(token) < 8192
    assert codec.verify(token, cfg.rules[0], context()).original == original


def test_request_crypto_performs_no_filesystem_or_network_io(pair, monkeypatch):
    import builtins
    import socket
    from pathlib import Path

    value, cfg = instance(pair), reversible()

    def forbidden(*_args, **_kwargs):
        pytest.fail(
            "Request-path crypto attempted configuration or network I/O"
        )

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    token = transform(value, "anna@example.org", cfg).value
    assert (
        value.restore(token, context=context(), config=cfg).value
        == "anna@example.org"
    )


def test_key_files_are_private_and_generation_never_overwrites(tmp_path):
    public, private = generate_pair(tmp_path / "keys")
    before = (public.read_bytes(), private.read_bytes())
    AsymmetricEnvelope(*before)
    if os.name == "posix":
        assert stat.S_IMODE(private.stat().st_mode) == 0o600
        assert stat.S_IMODE(public.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        generate_pair(tmp_path / "keys")
    assert (public.read_bytes(), private.read_bytes()) == before


def test_trusted_key_files_load_once_and_require_issuer_keyring(pair, tmp_path):
    (tmp_path / "public.pem").write_bytes(pair[0])
    (tmp_path / "private.pem").write_bytes(pair[1])
    options = {
        "root": tmp_path,
        "anonymization_public_key_file": "public.pem",
        "anonymization_private_key_file": "private.pem",  # pragma: allowlist secret - filename only
    }
    with pytest.raises(ValueError, match="key file is missing"):
        build_anonymization(AppSettings(**options))
    keyring = json.dumps(
        {"local-v1": base64.b64encode(bytes(range(32))).decode()}
    )
    workflow = build_anonymization(
        AppSettings(**options, anonymization_keys_json=keyring)
    )
    assert workflow.runtime is not None
    (tmp_path / "public.pem").unlink()
    (tmp_path / "private.pem").unlink()
    token = transform(workflow.runtime, "anna@example.org", reversible()).value
    assert token.startswith("[FFR2.")
    with pytest.raises(ValueError, match="Invalid private anonymization"):
        build_anonymization(
            AppSettings(**options, anonymization_keys_json=keyring)
        )
    with pytest.raises(ValueError, match="Both"):
        AppSettings(root=tmp_path, anonymization_public_key_file="public.pem")
    with pytest.raises(AnonymizationError, match="unavailable"):
        build_anonymization(AppSettings(root=tmp_path)).transform(
            {"prompt": token},
            context=context(),
            config=AnonymizationConfig(),
            direction="input",
            target="model",
        )
