"""Authenticated RSA-OAEP/AES-GCM envelopes; no per-token server storage."""

import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from fastfence.shared.anonymization import AnonymizationError

_FINGERPRINT_BYTES = 32
_WRAPPED_KEY_BYTES = 384
_NONCE_BYTES = 12
_MAC_BYTES = 32
_PREFIX_BYTES = _FINGERPRINT_BYTES + _WRAPPED_KEY_BYTES + _NONCE_BYTES
_DOMAIN = b"FastFence/anonymization/FFR2/envelope\x00"


def _oaep() -> padding.OAEP:
    return padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=b"FastFence/anonymization/FFR2/content-key",
    )


class AsymmetricEnvelope:
    """One trusted recipient pair; issuer authentication is supplied separately."""

    def __init__(self, public_pem: bytes, private_pem: bytes) -> None:
        try:
            if (
                not 1 <= len(public_pem) <= 16384
                or not 1 <= len(private_pem) <= 16384
            ):
                raise ValueError
            public = serialization.load_pem_public_key(public_pem)
            private = serialization.load_pem_private_key(
                private_pem, password=None
            )
            if not isinstance(public, rsa.RSAPublicKey) or not isinstance(
                private, rsa.RSAPrivateKey
            ):
                raise ValueError
            if public.key_size != 3072 or private.key_size != 3072:
                raise ValueError
            if public.public_numbers() != private.public_key().public_numbers():
                raise ValueError
            if public.public_numbers().e != 65537:
                raise ValueError
        except (ValueError, TypeError, UnsupportedAlgorithm):
            raise ValueError(
                "Invalid RSA-3072 anonymization key pair"
            ) from None
        self._public = public
        self._private = private
        self._fingerprint = hashlib.sha256(
            public.public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        ).digest()

    def encrypt(self, original: bytes, aad: bytes, issuer_key: bytes) -> bytes:
        content_key = AESGCM.generate_key(bit_length=256)
        wrapped = self._public.encrypt(content_key, _oaep())
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(content_key).encrypt(nonce, original, aad)
        body = self._fingerprint + wrapped + nonce + ciphertext
        authentication = hmac.digest(issuer_key, _DOMAIN + aad + body, "sha256")
        return body + authentication

    def decrypt(self, payload: bytes, aad: bytes, issuer_key: bytes) -> bytes:
        if len(payload) < _PREFIX_BYTES + 16 + _MAC_BYTES:
            raise AnonymizationError("anonymization_invalid_token")
        body, authentication = payload[:-_MAC_BYTES], payload[-_MAC_BYTES:]
        expected = hmac.digest(issuer_key, _DOMAIN + aad + body, "sha256")
        if not hmac.compare_digest(authentication, expected):
            raise AnonymizationError("anonymization_invalid_token")
        if not hmac.compare_digest(
            body[:_FINGERPRINT_BYTES], self._fingerprint
        ):
            raise AnonymizationError("anonymization_invalid_token")
        wrapped_end = _FINGERPRINT_BYTES + _WRAPPED_KEY_BYTES
        wrapped = body[_FINGERPRINT_BYTES:wrapped_end]
        nonce = body[wrapped_end:_PREFIX_BYTES]
        try:
            content_key = self._private.decrypt(wrapped, _oaep())
            if len(content_key) != 32:
                raise ValueError
            return AESGCM(content_key).decrypt(nonce, body[_PREFIX_BYTES:], aad)
        except (ValueError, InvalidTag):
            raise AnonymizationError("anonymization_invalid_token") from None
