from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response

from fastfence.app.interfaces.http.policy_authoring import (
    configure_policy_authoring,
)
from fastfence.app.interfaces.http.rule_authoring import (
    configure_rule_authoring,
)
from fastfence.app.interfaces.http.semantic_preview import (
    configure_semantic_preview,
)
from fastfence.app.interfaces.http.semantic_review import (
    configure_semantic_review,
)
from fastfence.modules.control.application.facade import ControlRuntime
from fastfence.modules.control.contracts.dto import (
    Identity,
    ModelCall,
    ToolCall,
    Verdict,
)
from fastfence.modules.control.domain.models import Policy
from fastfence.shared.request_size import request_size


def configure_http(app: FastAPI, runtime: ControlRuntime) -> None:
    _configure_safety(app)
    actor, admin = _authentication(runtime)
    _configure_public(app, runtime, actor)
    _configure_management(app, runtime, admin)
    configure_rule_authoring(app, admin)
    configure_semantic_preview(app, runtime, admin)
    configure_semantic_review(app, runtime, admin)
    configure_policy_authoring(app, runtime, admin)


def _configure_safety(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def invalid_request(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": "Invalid request schema"}
        )

    @app.middleware("http")
    async def browser_security(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        )
        return response


def _authentication(
    runtime: ControlRuntime,
) -> tuple[Callable[[Request], Identity], Callable[..., Identity]]:
    def actor(request: Request) -> Identity:
        authorization = request.headers.get("authorization", "")
        token = (
            authorization[7:] if authorization.startswith("Bearer ") else None
        )
        identity = runtime.authenticate(token)
        if identity is None:
            raise HTTPException(401, "Verified bearer credential required")
        return identity

    def admin(identity: Identity = Depends(actor)) -> Identity:
        if not identity.admin:
            raise HTTPException(403, "Management credential required")
        return identity

    return actor, admin


def _configure_public(
    app: FastAPI, runtime: ControlRuntime, actor: Callable[[Request], Identity]
) -> None:
    @app.get("/")
    def dashboard() -> FileResponse:
        return FileResponse(Path(__file__).parent / "web/index.html")

    @app.get("/assets/{script_name}")
    def dashboard_script(script_name: str) -> FileResponse:
        assets = {
            "rules.js",
            "playground.js",
            "policy-studio.js",
            "audit.js",
            "documents.js",
            "console.js",
            "policy-manager.js",
            "semantic-review.js",
            "semantic-regressions.js",
            "console.css",
            "logo.svg",
        }
        if script_name not in assets:
            raise HTTPException(404, "Unknown asset")
        return FileResponse(
            Path(__file__).parent / "web" / script_name,
            media_type=(
                "text/css"
                if script_name.endswith(".css")
                else "image/svg+xml"
                if script_name.endswith(".svg")
                else "text/javascript"
            ),
        )

    @app.get("/health")
    def health() -> dict[str, str | int]:
        snapshot = runtime.snapshot()
        return {
            "status": "ready",
            "scope": "liveness",
            "readiness_endpoint": "/ready",
            "policy_version": snapshot.policy.version,
            "semantic_provider": snapshot.policy.semantic.provider,
            "semantic_status": "disabled"
            if snapshot.policy.semantic.provider == "disabled"
            else "configured; verified per invocation",
        }

    @app.get("/ready")
    async def readiness() -> JSONResponse:
        report = await runtime.readiness()
        return JSONResponse(
            status_code=200 if report.status == "ready" else 503,
            content=report.model_dump(mode="json"),
        )

    @app.get("/api/me")
    def me(identity: Identity = Depends(actor)) -> Identity:
        return identity

    @app.post("/api/invoke")
    async def invoke(
        call: ToolCall, request: Request, identity: Identity = Depends(actor)
    ) -> Verdict:
        return await runtime.invoke(
            identity, call, preparation_bytes=request_size(request.scope)
        )

    @app.post("/api/models/complete")
    async def complete(
        call: ModelCall, request: Request, identity: Identity = Depends(actor)
    ) -> Verdict:
        return await runtime.invoke(
            identity, call, preparation_bytes=request_size(request.scope)
        )


def _configure_management(
    app: FastAPI, runtime: ControlRuntime, admin: Callable[..., Identity]
) -> None:
    @app.get("/api/admin/status", dependencies=[Depends(admin)])
    def status() -> dict[str, object]:
        return runtime.status()

    @app.post("/api/admin/reload")
    def reload_policy(identity: Identity = Depends(admin)) -> dict[str, int]:
        try:
            snapshot = runtime.reload_policy(identity)
            return {
                "policy_version": snapshot.policy.version,
                "feed_version": snapshot.feed.version,
            }
        except Exception:
            raise HTTPException(
                409,
                "Invalid policy/feed or non-increasing version; last good policy retained",
            ) from None

    @app.put("/api/admin/policy")
    def save_policy(
        policy: Policy, identity: Identity = Depends(admin)
    ) -> dict[str, int]:
        try:
            snapshot = runtime.save_policy(policy, identity)
            return {"policy_version": snapshot.policy.version}
        except Exception:
            raise HTTPException(
                409, "Policy not saved; validation/version conflict"
            ) from None

    @app.get("/api/admin/audit.jsonl", dependencies=[Depends(admin)])
    def audit_export() -> Response:
        import json

        content = (
            "\n".join(
                json.dumps(row) for row in reversed(runtime.audit(10_000))
            )
            + "\n"
        )
        return Response(
            content,
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": 'attachment; filename="fastfence-audit.jsonl"'
            },
        )
