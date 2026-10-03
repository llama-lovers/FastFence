from __future__ import annotations

import json
import threading
from pathlib import Path

import yaml

from fastfence.modules.control.domain.models import (
    Policy,
    SignatureFeed,
    Snapshot,
)


class PolicyStore:
    """Validate a complete candidate before publishing an immutable invocation snapshot."""

    def __init__(self, policy_path: Path, feed_path: Path) -> None:
        self.policy_path, self.feed_path = policy_path, feed_path
        self._lock = threading.Lock()
        self._snapshot = self._read()

    def _read(self) -> Snapshot:
        policy = Policy.model_validate(
            yaml.safe_load(self.policy_path.read_text())
        )
        feed = SignatureFeed.model_validate(
            json.loads(self.feed_path.read_text())
        )
        return Snapshot(policy=policy, feed=feed)

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                policy=self._snapshot.policy.model_copy(deep=True),
                feed=self._snapshot.feed.model_copy(deep=True),
            )

    def save(self, policy: Policy) -> Snapshot:
        # The feed is also validated before a new policy reaches disk or the active snapshot.
        feed = SignatureFeed.model_validate(
            json.loads(self.feed_path.read_text())
        )
        with self._lock:
            if policy.version <= self._snapshot.policy.version:
                raise ValueError("Policy version must increase on each save")
            if feed.version < self._snapshot.feed.version:
                raise ValueError("Signature feed version cannot decrease")
            temporary = self.policy_path.with_suffix(".yaml.tmp")
            temporary.write_text(
                yaml.safe_dump(policy.model_dump(), sort_keys=False)
            )
            temporary.replace(self.policy_path)
            self._snapshot = Snapshot(
                policy=policy.model_copy(deep=True), feed=feed
            )
            return self.snapshot_unlocked()

    def snapshot_unlocked(self) -> Snapshot:
        return Snapshot(
            policy=self._snapshot.policy.model_copy(deep=True),
            feed=self._snapshot.feed.model_copy(deep=True),
        )

    def reload(self) -> Snapshot:
        candidate = self._read()
        with self._lock:
            previous = self._snapshot
            if candidate.policy.version <= previous.policy.version:
                raise ValueError("Policy version must increase on each reload")
            if candidate.feed.version < previous.feed.version:
                raise ValueError("Signature feed version cannot decrease")
            self._snapshot = candidate
            return self.snapshot_unlocked()
