import uuid
from typing import Any

from fastfence.modules.control.contracts.ports import (
    IdentityPort,
    LedgerPort,
    PolicyPort,
)
from fastfence.modules.control.domain.limits import effective_limits
from fastfence.modules.control.domain.models import (
    Identity,
    Policy,
    Snapshot,
    Verdict,
)


class ManagementUseCases:
    def __init__(
        self, policies: PolicyPort, identities: IdentityPort, ledger: LedgerPort
    ) -> None:
        self.policies, self.identities, self.ledger = (
            policies,
            identities,
            ledger,
        )

    def status(self) -> dict[str, Any]:
        snapshot = self.policies.snapshot()
        budgets: list[dict[str, Any]] = []
        for row in self.ledger.budgets():
            identity = self.identities.by_subject(row["subject"])
            limits = (
                effective_limits(identity, snapshot.policy)
                if identity
                else None
            )
            budgets.append(
                {
                    **row,
                    "limits": limits.model_dump() if limits else None,
                    "roles": identity.roles if identity else [],
                }
            )
        return {
            "policy": snapshot.policy.model_dump(),
            "feed": snapshot.feed.model_dump(),
            "metrics": self.ledger.stats(),
            "budgets": budgets,
            "audit": self.ledger.audit(),
            "business_backend": "simulated",
            "budget_window": "UTC day; per trusted subject",
            "semantic_status": "disabled — deterministic controls only"
            if snapshot.policy.semantic.provider == "disabled"
            else "configured — actual model evaluated per invocation; errors fail closed",
        }

    def save(self, policy: Policy, identity: Identity) -> Snapshot:
        snapshot = self.policies.save(policy)
        self._audit_change(identity, "policy.save", "policy_saved")
        return snapshot

    def reload(self, identity: Identity) -> Snapshot:
        snapshot = self.policies.reload()
        self._audit_change(identity, "policy.reload", "policy_reloaded")
        return snapshot

    def _audit_change(
        self, identity: Identity, target: str, reason: str
    ) -> None:
        snapshot = self.policies.snapshot()
        self.ledger.append(
            identity.subject,
            identity.tenant,
            target,
            Verdict(
                request_id=uuid.uuid4().hex,
                decision="allowed",
                reason=reason,
                policy_version=snapshot.policy.version,
                feed_version=snapshot.feed.version,
                latency_ms=0,
                semantic_provider=snapshot.policy.semantic.provider,
            ),
        )
