"""Management-only semantic rule testing; never activates configuration."""

from collections.abc import Callable
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import Field, ValidationError

from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.domain.exceptions import ModelUnavailableError
from fastfence.modules.control.domain.semantic_rules import SemanticRule
from fastfence.shared.models import StrictModel


class SemanticPreviewRequest(StrictModel):
    rule: SemanticRule
    text: str = Field(min_length=1, max_length=4096)
    direction: Literal["input", "output"]
    target: Literal["model", "tool"]
    base_version: int = Field(ge=1)


def configure_semantic_preview(
    app: FastAPI, runtime: ControlRuntime, admin: Callable[..., Any]
) -> None:
    @app.post("/api/admin/semantic/preview", dependencies=[Depends(admin)])
    async def preview(request: SemanticPreviewRequest) -> dict[str, Any]:
        try:
            return await runtime.preview_semantic_rule(
                request.rule,
                request.text,
                request.direction,
                request.target,
                request.base_version,
            )
        except ValidationError:
            raise HTTPException(
                422, "Invalid candidate semantic configuration"
            ) from None
        except ValueError:
            raise HTTPException(
                409, "Policy changed. Refresh and test again."
            ) from None
        except (ModelUnavailableError, TimeoutError):
            raise HTTPException(
                503,
                "Laya text analysis is unavailable or busy. The rule was not activated; check setup and retry.",
            ) from None
