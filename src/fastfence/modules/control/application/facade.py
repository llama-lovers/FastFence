import json
import uuid
from typing import Any, Literal

from fastfence.modules.control.application.services.engine import Engine
from fastfence.modules.control.application.use_cases.content import (
    ContentUseCases,
)
from fastfence.modules.control.application.use_cases.management import (
    ManagementUseCases,
)
from fastfence.modules.control.application.use_cases.semantic_preview import (
    preview_semantic,
)
from fastfence.modules.control.contracts.ports import (
    AnonymizationPort,
    IdentityPort,
    LedgerPort,
    PolicyPort,
    ToolsPort,
)
from fastfence.modules.control.domain.models import (
    Identity,
    ModelCall,
    Policy,
    Snapshot,
    ToolCall,
    Verdict,
)
from fastfence.modules.control.domain.semantic_rules import SemanticRule
from fastfence.modules.control.persistence.identity import IdentityStore
from fastfence.modules.control.persistence.ledger import Ledger
from fastfence.modules.control.persistence.models import (
    OllamaModels,
    SemanticScanner,
)
from fastfence.modules.control.persistence.openai_models import OpenAIModels
from fastfence.modules.control.persistence.policy import PolicyStore
from fastfence.modules.control.persistence.secrets import OfflineSecrets
from fastfence.modules.control.persistence.tools import UnconfiguredTools
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

    async def prepare_document(
        self, identity: Identity, markdown: str, model: str | None = None
    ) -> Verdict:
        return await ContentUseCases(self.engine).prepare(
            identity, markdown, model
        )

    async def complete_document(
        self,
        identity: Identity,
        markdown: str,
        model: str | None = None,
        max_output_tokens: int = 256,
        restore_originals: bool = False,
    ) -> tuple[Verdict, str | None]:
        return await ContentUseCases(self.engine).complete(
            identity, markdown, model, max_output_tokens, restore_originals
        )

    async def preview_semantic_rule(
        self,
        rule: SemanticRule,
        text: str,
        direction: Literal["input", "output"],
        target: Literal["model", "tool"],
        base_version: int,
    ) -> dict[str, Any]:
        return await preview_semantic(
            self.engine, rule, text, direction, target, base_version
        )

    def status(self) -> dict[str, Any]:
        status = self.management.status()
        configured = list(self.snapshot().policy.tools)
        connected = [
            name for name in configured if self.engine.tools.supports(name)
        ]
        status["tools"] = {
            "connected": connected,
            "unavailable": sorted(set(configured) - set(connected)),
        }
        status["business_backend"] = (
            "connected" if connected else "not_configured"
        )
        return status

    async def refresh_config(self) -> bool:
        return await self.policies.refresh()

    def diagnostics(self) -> dict[str, Any]:
        return self.policies.diagnostics()

    def save_policy(
        self,
        policy: Policy,
        identity: Identity,
        *,
        expected_feed_version: int | None = None,
        expected_base_policy: Policy | None = None,
    ) -> Snapshot:
        return self.management.save(
            policy,
            identity,
            expected_feed_version=expected_feed_version,
            expected_base_policy=expected_base_policy,
        )

    def reload_policy(self, identity: Identity) -> Snapshot:
        return self.management.reload(identity)

    def audit(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.ledger.audit(limit)

    async def aclose(self) -> None:
        close = getattr(self.engine.scanner, "aclose", None)
        if close is not None:
            await close()
        self.close()

    def close(self) -> None:
        self.ledger.close()
        if self.engine.anonymization is not None:
            self.engine.anonymization.close()


def build_runtime(
    settings: AppSettings,
    *,
    anonymization: AnonymizationPort | None = None,
    tools: ToolsPort | None = None,
) -> ControlRuntime:
    identities = (
        IdentityStore(records=json.loads(settings.identity_config_json))
        if settings.identity_config_json is not None
        else IdentityStore(
            settings.identity_config_file
            or settings.state_path / "identities.json"
        )
    )
    policies = PolicyStore(
        settings.root / "config/policy.yaml",
        settings.root / "config/signatures.json",
        config_url=settings.config_url,
        poll_interval=settings.config_poll_interval,
        fetch_timeout=settings.config_fetch_timeout,
        max_source_bytes=settings.max_config_source_bytes,
    )
    ledger = Ledger(
        instance_id=settings.instance_id or uuid.uuid4().hex,
        audit_limit=settings.audit_limit,
    )
    engine = Engine(
        policies=policies,
        ledger=ledger,
        tools=tools if tools is not None else UnconfiguredTools(),
        scanner=SemanticScanner(
            settings.ollama_url,
            settings.kev_url,
            settings.authoring_root or settings.root,
        ),
        models=OpenAIModels(settings.openai_base_url, settings.openai_api_key)
        if settings.model_provider == "openai"
        else OllamaModels(settings.ollama_url),
        secrets=OfflineSecrets(
            tuple(settings.secret_plugin_files),
            settings.secret_plugin_max_file_bytes,
        ),
        anonymization=anonymization,
    )
    return ControlRuntime(
        identities=identities, policies=policies, ledger=ledger, engine=engine
    )
