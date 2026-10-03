from __future__ import annotations

from fastfence.modules.control.domain.models import Policy


def configure_policy(engine, mutate):
    """Prepare a validated candidate without mutating the published snapshot."""
    data = engine.policies.snapshot().policy.editable()
    data["version"] += 1
    mutate(data)
    policy = Policy.model_validate(data)
    engine.policies.save(policy)
    return policy
