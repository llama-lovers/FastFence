"""Independent module boundary: static keys and request-local buffers only."""

import time
from collections.abc import Callable, Mapping
from typing import Any

from fastfence.modules.anonymization.application.services.transform import (
    AnonymizationService,
)
from fastfence.modules.anonymization.persistence.asymmetric import (
    AsymmetricEnvelope,
)
from fastfence.modules.anonymization.persistence.crypto import (
    StatelessTokenCodec,
)
from fastfence.shared.anonymization import (
    AnonymizationConfig,
    AnonymizationContext,
    AnonymizationDirection,
    AnonymizationResult,
    AnonymizationTarget,
)


class AnonymizationRuntime:
    def __init__(
        self,
        *,
        keyring: Mapping[str, bytes],
        current_key_id: str,
        ttl_seconds: int = 1800,
        max_value_bytes: int = 4096,
        max_token_bytes: int = 8192,
        max_replacements: int = 256,
        public_key_pem: bytes | None = None,
        private_key_pem: bytes | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (public_key_pem is None) != (private_key_pem is None):
            raise ValueError(
                "Both anonymization public and private keys are required"
            )
        envelope = (
            AsymmetricEnvelope(public_key_pem, private_key_pem)
            if public_key_pem is not None and private_key_pem is not None
            else None
        )
        self._codec = StatelessTokenCodec(
            keyring=keyring,
            current_key_id=current_key_id,
            ttl_seconds=ttl_seconds,
            max_value_bytes=max_value_bytes,
            max_token_bytes=max_token_bytes,
            clock=clock,
            asymmetric_envelope=envelope,
        )
        self._service = AnonymizationService(
            self._codec, max_replacements=max_replacements
        )

    def transform(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        direction: AnonymizationDirection,
        target: AnonymizationTarget,
    ) -> AnonymizationResult:
        return self._service.transform(
            value,
            context=context,
            config=config,
            direction=direction,
            target=target,
        )

    def restore(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: AnonymizationTarget = "model",
    ) -> AnonymizationResult:
        return self._service.restore(
            value, context=context, config=config, target=target
        )

    def reveal_for_checks(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: AnonymizationTarget,
    ) -> AnonymizationResult:
        return self._service.reveal_for_checks(
            value, context=context, config=config, target=target
        )

    def close(self) -> None:
        # No session state, plaintext maps or handles exist to retain or release.
        pass
