"""Reviewed-library AEAD and scoped identifiers; static keys, no value storage."""

import base64
import hmac
import json
import os
import time
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Literal

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from fastfence.modules.anonymization.domain.tokens import (
    VerifiedToken,
    parse_token,
)
from fastfence.shared.anonymization import (
    AnonymizationContext,
    AnonymizationError,
    AnonymizationRule,
)


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decoded(value: str) -> bytes:
    try:
        data = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        if _encoded(data) != value:
            raise ValueError
        return data
    except ValueError:
        raise AnonymizationError("anonymization_invalid_token") from None


def _scope(context: AnonymizationContext, rule: AnonymizationRule) -> bytes:
    return json.dumps(
        [
            "FastFence/anonymization/v1",
            context.tenant,
            context.subject,
            rule.fingerprint,
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def _aad(
    header: str, context: AnonymizationContext, rule: AnonymizationRule
) -> bytes:
    return header.encode("ascii") + b"\x00" + _scope(context, rule)


class StatelessTokenCodec:
    def __init__(
        self,
        *,
        keyring: Mapping[str, bytes],
        current_key_id: str,
        ttl_seconds: int = 1800,
        max_value_bytes: int = 4096,
        max_token_bytes: int = 8192,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not keyring or current_key_id not in keyring or len(keyring) > 16:
            raise ValueError("Invalid anonymization key configuration")
        if not (
            1 <= ttl_seconds <= 86400
            and 1 <= max_value_bytes <= 4096
            and 128 <= max_token_bytes <= 16384
        ):
            raise ValueError("Invalid anonymization limits")
        prepared = {}
        for key_id, key in keyring.items():
            if (
                not 1 <= len(key_id) <= 16
                or any(
                    char
                    not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                    for char in key_id
                )
                or not isinstance(key, bytes)
                or len(key) != 32
            ):
                raise ValueError("Invalid anonymization key configuration")
            material = [
                HKDF(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=None,
                    info=b"FastFence/anonymization/" + label,
                ).derive(key)
                for label in (
                    b"identifier/v1",
                    b"label-auth/v1",
                    b"value-aead/v1",
                )
            ]
            prepared[key_id] = (material[0], material[1], AESGCM(material[2]))
        self._keys = MappingProxyType(prepared)
        self.current_key_id = current_key_id
        self.ttl_seconds = ttl_seconds
        self.max_value_bytes = max_value_bytes
        self.max_token_bytes = max_token_bytes
        self.clock = clock

    @staticmethod
    def _identifier(
        key: bytes,
        original: bytes,
        context: AnonymizationContext,
        rule: AnonymizationRule,
    ) -> str:
        return _encoded(
            hmac.digest(
                key, _scope(context, rule) + b"\x00" + original, "sha256"
            )[:16]
        )

    def issue(
        self,
        rule: AnonymizationRule,
        original: str,
        context: AnonymizationContext,
        mode: Literal["irreversible", "reversible"],
    ) -> str:
        raw = original.encode()
        if len(raw) > self.max_value_bytes:
            raise AnonymizationError("anonymization_value_too_large")
        id_key, mac_key, cipher = self._keys[self.current_key_id]
        identifier = self._identifier(id_key, raw, context, rule)
        version = "FFI1" if mode == "irreversible" else "FFR1"
        fields = [
            version,
            self.current_key_id,
            rule.id,
            rule.replacement,
            identifier,
        ]
        if mode == "reversible":
            fields.append(str(int(self.clock()) + self.ttl_seconds))
        header = ".".join(fields)
        aad = _aad(header, context, rule)
        if mode == "irreversible":
            payload = _encoded(hmac.digest(mac_key, aad, "sha256")[:16])
        else:
            nonce = os.urandom(12)
            payload = _encoded(nonce + cipher.encrypt(nonce, raw, aad))
        token = f"[{header}.{payload}]"
        if len(token) > self.max_token_bytes:
            raise AnonymizationError("anonymization_token_too_large")
        return token

    def verify(
        self, token: str, rule: AnonymizationRule, context: AnonymizationContext
    ) -> VerifiedToken:
        if len(token.encode()) > self.max_token_bytes:
            raise AnonymizationError("anonymization_token_too_large")
        fields = parse_token(token)
        material = self._keys.get(fields.key_id)
        if (
            material is None
            or fields.rule_id != rule.id
            or fields.prefix != rule.replacement
        ):
            raise AnonymizationError("anonymization_invalid_token")
        id_key, mac_key, cipher = material
        header = token[1:-1].rsplit(".", 1)[0]
        aad = _aad(header, context, rule)
        payload = _decoded(fields.payload)
        if fields.version == "FFI1":
            if not hmac.compare_digest(
                payload, hmac.digest(mac_key, aad, "sha256")[:16]
            ):
                raise AnonymizationError("anonymization_invalid_token")
            return VerifiedToken(
                rule_id=rule.id,
                identifier=fields.identifier,
                mode="irreversible",
            )
        try:
            raw = cipher.decrypt(payload[:12], payload[12:], aad)
            if len(raw) > self.max_value_bytes:
                raise AnonymizationError("anonymization_value_too_large")
            original = raw.decode("utf-8")
        except (InvalidTag, ValueError):
            raise AnonymizationError("anonymization_invalid_token") from None
        expected = self._identifier(id_key, raw, context, rule)
        if not hmac.compare_digest(fields.identifier, expected):
            raise AnonymizationError("anonymization_invalid_token")
        if fields.expiry is None or int(fields.expiry) <= self.clock():
            raise AnonymizationError("anonymization_token_expired")
        return VerifiedToken(
            original=original,
            rule_id=rule.id,
            identifier=expected,
            mode="reversible",
        )
