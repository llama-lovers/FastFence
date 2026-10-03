from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from pydantic import Field

from fastfence.modules.control.domain.text_rules import (
    TextRule,
    text_rule_matches,
)
from fastfence.shared.models import StrictModel


class RulePreview(StrictModel):
    rule: TextRule
    samples: list[Annotated[str, Field(max_length=4096)]] = Field(
        default_factory=list, max_length=16
    )


class RulePreviewResult(StrictModel):
    rule: TextRule
    matches: list[bool]


def configure_rule_authoring(app: FastAPI, admin: Callable[..., Any]) -> None:
    @app.get("/api/admin/rules/schema", dependencies=[Depends(admin)])
    def rule_schema() -> dict[str, Any]:
        return TextRule.model_json_schema()

    @app.post("/api/admin/rules/preview", dependencies=[Depends(admin)])
    def preview_rule(request: RulePreview) -> RulePreviewResult:
        return RulePreviewResult(
            rule=request.rule,
            matches=[
                text_rule_matches(request.rule, sample)
                for sample in request.samples
            ],
        )
