from typing import Any

from fastfence.modules.control.application.services.engine import Engine
from fastfence.modules.control.application.use_cases.management import (
    ManagementUseCases,
)
from fastfence.modules.control.contracts.ports import (
    IdentityPort,
    LedgerPort,
    PolicyPort,
)
from fastfence.modules.control.domain.models import (
    Identity,
    ModelCall,
    Policy,
    Snapshot,
    ToolCall,
    Verdict,
)
from fastfence.modules.control.persistence.identity import IdentityStore
from fastfence.modules.control.persistence.ledger import Ledger
from fastfence.modules.control.persistence.models import (
    OllamaModels,
    SemanticScanner,
)
from fastfence.modules.control.persistence.policy import PolicyStore
from fastfence.modules.control.persistence.tools import DemoTools
from fastfence.shared.settings.app_settings import AppSettings


class ControlRuntime:
    """Feature composition and its public application boundary."""

    def __init__(
        self,
        identities: IdentityPort,
        policies: PolicyPort,
        ledger: LedgerPort,
        engine: Engine,
    ) -> None:
        self.identities, self.policies, self.ledger, self.engine = (
            identities,
            policies,
            ledger,
            engine,
        )
        self.management = ManagementUseCases(policies, identities, ledger)

    def authenticate(self, token: str | None) -> Identity | None:
        return self.identities.authenticate(token)

    def snapshot(self) -> Snapshot:
        return self.policies.snapshot()

    async def invoke(
        self, identity: Identity, call: ToolCall | ModelCall
    ) -> Verdict:
        return await self.engine.invoke(identity, call)

    def status(self) -> dict[str, Any]:
        return self.management.status()

    def save_policy(self, policy: Policy, identity: Identity) -> Snapshot:
        return self.management.save(policy, identity)

    def reload_policy(self, identity: Identity) -> Snapshot:
        return self.management.reload(identity)

    def audit(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.ledger.audit(limit)

    def close(self) -> None:
        self.ledger.close()


def build_runtime(settings: AppSettings) -> ControlRuntime:
    identities = IdentityStore(settings.state_path / "identities.json")
    policies = PolicyStore(
        settings.root / "config/policy.yaml",
        settings.root / "config/signatures.json",
    )
    ledger = Ledger(settings.state_path / "ledger.sqlite3")
    engine = Engine(
        policies=policies,
        ledger=ledger,
        tools=DemoTools(),
        scanner=SemanticScanner(settings.ollama_url, settings.kev_url),
        models=OllamaModels(settings.ollama_url),
    )
    return ControlRuntime(
        identities=identities, policies=policies, ledger=ledger, engine=engine
    )
