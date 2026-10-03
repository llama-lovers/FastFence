from collections.abc import Callable
from typing import Any

from fastapi import Depends, FastAPI, HTTPException

from fastfence.app.interfaces.http.authoring_process import (
    LayaPolicyAuthor,
    PolicyAuthoringError,
)
from fastfence.app.interfaces.http.authoring_records import (
    ActivateRequest,
    ActivationView,
    DraftRequest,
    PreviewRequest,
    PreviewView,
    ProposalView,
)
from fastfence.app.interfaces.http.authoring_session import (
    PolicyAuthoringSession,
)
from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.domain.models import Identity


def configure_policy_authoring(
    app: FastAPI, runtime: ControlRuntime, admin: Callable[..., Any]
) -> None:
    app.state.policy_authoring = PolicyAuthoringSession(
        runtime,
        LayaPolicyAuthor(app.state.settings),
        tests_path=app.state.settings.root / "config/policy-tests.yaml",
    )

    @app.post("/api/admin/policies/draft")
    async def draft_policy(
        request: DraftRequest, identity: Identity = Depends(admin)
    ) -> ProposalView:
        try:
            return await app.state.policy_authoring.draft(request, identity)
        except PolicyAuthoringError as error:
            raise HTTPException(error.status, error.code) from None

    @app.post("/api/admin/policies/preview")
    def preview_policy(
        request: PreviewRequest, identity: Identity = Depends(admin)
    ) -> PreviewView:
        try:
            return app.state.policy_authoring.preview(request, identity)
        except PolicyAuthoringError as error:
            raise HTTPException(error.status, error.code) from None

    @app.post("/api/admin/policies/activate")
    def activate_policy(
        request: ActivateRequest, identity: Identity = Depends(admin)
    ) -> ActivationView:
        try:
            return app.state.policy_authoring.activate(
                request.proposal_id, request.base_version, identity
            )
        except PolicyAuthoringError as error:
            raise HTTPException(error.status, error.code) from None
