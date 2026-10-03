from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from fastfence.modules.control.domain.models import (
    Policy,
    Snapshot,
)
from fastfence.modules.control.persistence.config_providers import (
    ConfigProvider,
    ConfigSourceError,
    FileConfigProvider,
    HttpConfigProvider,
    sanitized_error,
)


def fingerprints(snapshot: Snapshot) -> tuple[str, str]:
    digests = [
        hashlib.sha256(
            json.dumps(model.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        for model in (snapshot.policy, snapshot.feed)
    ]
    return digests[0], digests[1]


class PolicyStore:
    """Publish complete immutable snapshots; enforcement acquires a reference."""

    def __init__(
        self,
        policy_path: Path,
        feed_path: Path,
        *,
        config_url: str | None = None,
        poll_interval: float = 2.0,
        fetch_timeout: float = 5.0,
        max_source_bytes: int = 262_144,
    ) -> None:
        self.policy_path, self.feed_path = policy_path, feed_path
        self.poll_interval = poll_interval
        self.provider: ConfigProvider = (
            HttpConfigProvider(config_url, fetch_timeout, max_source_bytes)
            if config_url
            else FileConfigProvider(policy_path, feed_path, max_source_bytes)
        )
        self._lock, self._refresh_lock = threading.Lock(), threading.Lock()
        try:
            self._snapshot = self._read()
        except Exception as error:
            raise ConfigSourceError(sanitized_error(error)) from None
        self._fingerprints = fingerprints(self._snapshot)
        now = datetime.now(UTC).isoformat()
        self._diagnostics: dict[str, Any] = {
            "source_kind": self.provider.kind,
            "management_writable": self.provider.kind == "local_files",
            "poll_interval_seconds": poll_interval,
            "generation": 1,
            "refresh_successes": 0,
            "refresh_failures": 0,
            "last_checked_at": now,
            "last_success_at": now,
            "last_error": None,
        }

    def _read(
        self,
        policy: Policy | None = None,
        *,
        expected_base_policy: Policy | None = None,
    ) -> Snapshot:
        data = self.provider.read()
        if expected_base_policy is not None and (
            Policy.model_validate(data["policy"]) != expected_base_policy
            or self._snapshot.policy != expected_base_policy
        ):
            raise ConfigSourceError("source_policy_conflict")
        if policy is not None:
            data["policy"] = policy.model_dump(mode="json")
        return Snapshot.model_validate(data)

    def snapshot(self) -> Snapshot:
        # Policy/feed models and their nested containers are deeply immutable.
        return self._snapshot

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._diagnostics)

    def _validate_versions(
        self, candidate: Snapshot, digests: tuple[str, str]
    ) -> bool:
        previous = self._snapshot
        versions = (candidate.policy.version, candidate.feed.version)
        old_versions = (previous.policy.version, previous.feed.version)
        for current, old, digest, old_digest in zip(
            versions, old_versions, digests, self._fingerprints, strict=True
        ):
            if current < old or (current == old and digest != old_digest):
                raise ConfigSourceError("version_conflict")
        return versions != old_versions

    def _publish(self, candidate: Snapshot, *, persist: bool = False) -> bool:
        digests = fingerprints(candidate)
        with self._lock:
            changed = self._validate_versions(candidate, digests)
            if persist:
                self._persist_policy(candidate.policy)
            if changed:
                self._snapshot, self._fingerprints = candidate, digests
                self._diagnostics["generation"] += 1
            now = datetime.now(UTC).isoformat()
            self._diagnostics.update(
                refresh_successes=self._diagnostics["refresh_successes"] + 1,
                last_checked_at=now,
                last_success_at=now,
                last_error=None,
            )
        return changed

    def _persist_policy(self, policy: Policy) -> None:
        if self.provider.kind != "local_files":
            return
        temporary = self.policy_path.with_suffix(".yaml.tmp")
        temporary.write_text(
            yaml.safe_dump(policy.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        temporary.replace(self.policy_path)

    def _failure(self, error: Exception) -> None:
        with self._lock:
            self._diagnostics.update(
                refresh_failures=self._diagnostics["refresh_failures"] + 1,
                last_checked_at=datetime.now(UTC).isoformat(),
                last_error=sanitized_error(error),
            )

    def _refresh(
        self,
        policy: Policy | None = None,
        *,
        expected_feed_version: int | None = None,
        expected_base_policy: Policy | None = None,
    ) -> bool:
        with self._refresh_lock:
            try:
                candidate = self._read(
                    policy, expected_base_policy=expected_base_policy
                )
                if expected_feed_version is not None and (
                    candidate.feed.version != expected_feed_version
                    or self._snapshot.feed.version != expected_feed_version
                ):
                    raise ConfigSourceError("feed_version_conflict")
                if (
                    policy is not None
                    and policy.version <= self._snapshot.policy.version
                ):
                    raise ConfigSourceError("version_conflict")
                return self._publish(candidate, persist=policy is not None)
            except Exception as error:
                self._failure(error)
                raise ConfigSourceError(
                    self.diagnostics()["last_error"]
                ) from None

    def save(
        self,
        policy: Policy,
        *,
        expected_feed_version: int | None = None,
        expected_base_policy: Policy | None = None,
    ) -> Snapshot:
        if self.provider.kind != "local_files":
            error = ConfigSourceError("read_only_source")
            self._failure(error)
            raise error
        self._refresh(
            policy,
            expected_feed_version=expected_feed_version,
            expected_base_policy=expected_base_policy,
        )
        return self.snapshot()

    def reload(self) -> Snapshot:
        self._refresh()
        return self.snapshot()

    async def refresh(self) -> bool:
        try:
            return await asyncio.to_thread(self._refresh)
        except ConfigSourceError:
            return False
