"""Authenticated management routes for explicit semantic review and activation."""

from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import ValidationError

from fastfence.app.interfaces.http.semantic_review_models import (
    SemanticActivateRequest,
    SemanticReviewError,
    SemanticReviewRequest,
    SemanticReviewView,
)
from fastfence.app.interfaces.http.semantic_review_session import (
    SemanticReviewSession,
)
from fastfence.app.interfaces.http.semantic_suite_store import (
    SemanticSuiteStore,
    SuiteStorageError,
)
from fastfence.app.interfaces.http.semantic_suites import (
    configure_semantic_suites,
)
from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.domain.models import Identity


def configure_semantic_review(
    app: FastAPI, runtime: ControlRuntime, admin: Callable[..., Any]
) -> None:
    store = SemanticSuiteStore(app.state.settings.root)
    session = SemanticReviewSession(runtime, store)
    app.state.semantic_review = session
    configure_semantic_suites(app, runtime, admin, session, store)

    @app.post("/api/admin/semantic/review")
    async def review(
        request: SemanticReviewRequest, identity: Identity = Depends(admin)
    ) -> SemanticReviewView:
        try:
            return await session.review(request, identity)
        except SemanticReviewError as error:
            raise HTTPException(error.status, error.reason) from None
        except ValidationError:
            raise HTTPException(422, "invalid_semantic_candidate") from None
        except SuiteStorageError:
            raise HTTPException(409, "semantic_suite_unavailable") from None

    @app.post("/api/admin/semantic/activate")
    def activate(
        request: SemanticActivateRequest, identity: Identity = Depends(admin)
    ) -> dict[str, Any]:
        try:
            return session.activate(request, identity)
        except SemanticReviewError as error:
            raise HTTPException(error.status, error.reason) from None
        except (SuiteStorageError, ValidationError):
            raise HTTPException(409, "semantic_suite_unavailable") from None
