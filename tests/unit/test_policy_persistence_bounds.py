"""Published file policies must remain readable under the same startup limits."""

import pytest
import yaml

from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.persistence.config_providers import (
    ConfigSourceError,
)
from fastfence.modules.control.persistence.policy import PolicyStore


def candidate(path, count=4, description="Updated policy"):
    data = yaml.safe_load(path.read_text())
    data["version"] += 1
    data["description"] = description
    data["text_rules"] = [
        {"id": f"rule-{i}", "value": "x" * 128, "operator": "contains"}
        for i in range(count)
    ]
    return Policy.model_validate(data)


def assert_original_remains(store, original, policy_path, feed_path, source):
    assert store.snapshot() is original
    assert policy_path.read_bytes() == source
    assert not policy_path.with_suffix(".yaml.tmp").exists()
    assert store.diagnostics()["last_error"] == "source_too_large"
    assert store.reload().policy == original.policy
    restarted = PolicyStore(
        policy_path, feed_path, max_source_bytes=store.max_source_bytes
    )
    assert restarted.snapshot().policy == original.policy


def test_large_policy_write_preserves_reloadable_last_good_source(project):
    policy_path = project / "config/policy.yaml"
    feed_path = project / "config/signatures.json"
    source = policy_path.read_bytes()
    limit = max(len(source), feed_path.stat().st_size) + 512
    store = PolicyStore(policy_path, feed_path, max_source_bytes=limit)
    original = store.snapshot()
    with pytest.raises(ConfigSourceError, match="^source_too_large$"):
        store.save(candidate(policy_path, count=64))
    assert_original_remains(store, original, policy_path, feed_path, source)


@pytest.mark.parametrize("offset", [-1, 0])
@pytest.mark.parametrize("description", ["Plain policy", "Żółć😀" * 40])
def test_serialized_byte_boundary_including_unicode(
    project, offset, description
):
    policy_path = project / "config/policy.yaml"
    feed_path = project / "config/signatures.json"
    source = policy_path.read_bytes()
    proposed = candidate(policy_path, description=description)
    serialized = yaml.safe_dump(
        proposed.model_dump(mode="json"), sort_keys=False
    ).encode("utf-8")
    limit = len(serialized) + offset
    assert max(len(source), feed_path.stat().st_size) < limit
    store = PolicyStore(policy_path, feed_path, max_source_bytes=limit)
    original = store.snapshot()
    if offset == -1:
        with pytest.raises(ConfigSourceError, match="^source_too_large$"):
            store.save(proposed)
        assert_original_remains(store, original, policy_path, feed_path, source)
    else:
        assert store.save(proposed).policy == proposed
        assert policy_path.read_bytes() == serialized
        assert store.reload().policy == proposed
        restarted = PolicyStore(policy_path, feed_path, max_source_bytes=limit)
        assert restarted.snapshot().policy == proposed
