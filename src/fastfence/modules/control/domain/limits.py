from fastfence.modules.control.domain.models import Identity, Limits, Policy


def effective_limits(identity: Identity, policy: Policy) -> Limits | None:
    budgets = [policy.budgets[r] for r in identity.roles if r in policy.budgets]
    if not budgets:
        return None
    return Limits(
        calls=min(b.calls for b in budgets),
        tokens=min(b.tokens for b in budgets),
        cost_microusd=min(b.cost_microusd for b in budgets),
        compute_ms=min(b.compute_ms for b in budgets),
        concurrent=min(b.concurrent for b in budgets),
    )
