"""Compose independent features and preserve model protocol metadata."""

import base64
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from fastfence.modules.anonymization.application.facade import (
    AnonymizationRuntime,
)
from fastfence.shared.anonymization import (
    AnonymizationConfig,
    AnonymizationContext,
    AnonymizationError,
    AnonymizationResult,
)
from fastfence.shared.settings.app_settings import AppSettings


def model_content(value: Any) -> tuple[Any, list[tuple[Any, Any]], list[Any]]:
    payload = deepcopy(value)
    positions: list[tuple[Any, Any]] = []
    if isinstance(payload, dict):
        positions.extend(
            (payload, key)
            for key in ("prompt", "text", "stop")
            if key in payload
        )
        for message in payload.get("messages", []):
            if isinstance(message, dict) and "content" in message:
                positions.append((message, "content"))
    return payload, positions, [container[key] for container, key in positions]


def build_anonymization(settings: AppSettings) -> "AnonymizationWorkflow":
    if (
        settings.anonymization_keys_json is not None
        and settings.anonymization_keys_file is not None
    ):
        raise ValueError("Choose one private anonymization key source")
    path = (
        settings.anonymization_keys_file
        or settings.state_path / "anonymization-keys.json"
    )
    if settings.anonymization_keys_json is None and not path.exists():
        if (
            settings.anonymization_keys_file is not None
            or settings.anonymization_public_key_file is not None
        ):
            raise ValueError("Private anonymization key file is missing")
        return AnonymizationWorkflow()
    try:
        if settings.anonymization_keys_json is not None:
            raw = settings.anonymization_keys_json.get_secret_value()
        else:
            with path.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError("Private anonymization key file is too large")
        entries = json.loads(raw)
        if not isinstance(entries, dict) or not entries:
            raise ValueError
        keys = {
            key: base64.b64decode(value, validate=True)
            for key, value in entries.items()
        }
        runtime = AnonymizationRuntime(
            keyring=keys,
            current_key_id=settings.anonymization_key_id,
            ttl_seconds=settings.anonymization_ttl_seconds,
            public_key_pem=_read_pem(settings.anonymization_public_key_file),
            private_key_pem=_read_pem(settings.anonymization_private_key_file),
        )
    except Exception:
        raise ValueError(
            "Invalid private anonymization key configuration"
        ) from None
    return AnonymizationWorkflow(runtime)


def _read_pem(path: Path | None) -> bytes | None:
    if path is None:
        return None
    with path.open("rb") as stream:
        value = stream.read(16385)
    if len(value) > 16384:
        raise ValueError("Anonymization PEM file is too large")
    return value


class AnonymizationWorkflow:
    def __init__(self, runtime: AnonymizationRuntime | None = None) -> None:
        self.runtime = runtime

    @staticmethod
    def _unavailable(
        value: Any, config: AnonymizationConfig
    ) -> AnonymizationResult:
        if config.enabled or any(
            marker in str(value).upper()
            for marker in ("FFI1.", "FFR1.", "FFR2.")
        ):
            raise AnonymizationError("anonymization_unavailable")
        return AnonymizationResult(value=value)

    @staticmethod
    def _content(
        value: Any, target: str, action: Callable[[Any], AnonymizationResult]
    ) -> AnonymizationResult:
        if target == "tool":
            return action(value)
        payload, positions, content = model_content(value)
        result = action(content)
        for (container, key), transformed in zip(
            positions, result.value, strict=True
        ):
            container[key] = transformed
        return result.model_copy(update={"value": payload})

    def transform(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        direction: Literal["input", "output"],
        target: Literal["model", "tool"],
    ) -> AnonymizationResult:
        runtime = self.runtime
        if runtime is None:
            return self._unavailable(value, config)
        return self._content(
            value,
            target,
            lambda content: runtime.transform(
                content,
                context=context,
                config=config,
                direction=direction,
                target=target,
            ),
        )

    def restore(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: Literal["model", "tool"],
    ) -> AnonymizationResult:
        runtime = self.runtime
        if runtime is None:
            return self._unavailable(value, config)
        return self._content(
            value,
            target,
            lambda content: runtime.restore(
                content,
                context=context,
                config=config,
                target=target,
            ),
        )

    def reveal_for_checks(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: Literal["model", "tool"],
    ) -> AnonymizationResult:
        runtime = self.runtime
        if runtime is None:
            return self._unavailable(value, config)
        return self._content(
            value,
            target,
            lambda content: runtime.reveal_for_checks(
                content,
                context=context,
                config=config,
                target=target,
            ),
        )

    def scratch(self) -> "AnonymizationWorkflow":
        return AnonymizationWorkflow(self.runtime)

    def close(self) -> None:
        if self.runtime is not None:
            self.runtime.close()
