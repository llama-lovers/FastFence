"""Dependency readiness reports deliberately exclude inference guarantees."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import ConfigDict

from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.shared.models import StrictModel


class ReadinessReport(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ready", "not_ready"]
    scope: Literal["required_semantic_prerequisites"] = (
        "required_semantic_prerequisites"
    )
    semantic_provider: str
    reason: Literal[
        "not_required",
        "prerequisites_checked",
        "laya_installation_unavailable",
        "model_unavailable",
        "probe_timeout",
        "provider_probe_unsupported",
        "probe_failed",
        "probe_not_configured",
    ]
    checked_at: datetime
    cache_ttl_seconds: int = 10
    inference_tested: bool = False
    business_upstreams_checked: bool = False
    ocr_checked: bool = False


class ReadinessPort(Protocol):
    async def check(self, config: SemanticConfig) -> ReadinessReport: ...
