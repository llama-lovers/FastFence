from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response

from fastfence.actions.tools import DemoTools
from fastfence.adapters.mcp import create_mcp
from fastfence.adapters.models import OllamaModels, SemanticScanner
from fastfence.core.engine import Engine
from fastfence.core.identity import IdentityStore
from fastfence.core.policy import PolicyStore
from fastfence.core.schema import Identity, ModelCall, Policy, ToolCall, Verdict
from fastfence.data.ledger import Ledger


@dataclass
class Settings:
    root: Path
    state: Path
    ollama_url: str = "http://127.0.0.1:11434"
    kev_url: str = "http://127.0.0.1:8009"

    @classmethod
    def environment(cls):
        root = Path(os.environ.get("FASTFENCE_ROOT", ".")).resolve()
        return cls(
            root=root,
            state=Path(os.environ.get("FASTFENCE_STATE", str(root / "state"))),
            ollama_url=os.environ.get("FASTFENCE_OLLAMA_URL", "http://127.0.0.1:11434"),
            kev_url=os.environ.get("FASTFENCE_KEV_URL", "http://127.0.0.1:8009"),
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.environment()
    identities = IdentityStore(settings.state / "identities.json")
    policies = PolicyStore(
        settings.root / "config/policy.yaml", settings.root / "config/signatures.json"
    )
    ledger = Ledger(settings.state / "ledger.sqlite3")
    engine = Engine(
        policies,
        ledger,
        DemoTools(),
        SemanticScanner(settings.ollama_url, settings.kev_url),
        OllamaModels(settings.ollama_url),
    )
    mcp = create_mcp(engine, identities)
    mcp_app = mcp.http_app(path="/", stateless_http=True, json_response=True)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_app.lifespan(app):
            try:
                yield
            finally:
                ledger.close()

    app = FastAPI(title="FastFence", version="0.1.0", lifespan=lifespan)
    app.state.engine, app.state.identities, app.state.settings = engine, identities, settings

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Framework validation errors normally echo user input, which may include a secret.
        return JSONResponse(status_code=422, content={"detail": "Invalid request schema"})

    @app.middleware("http")
    async def browser_security(request: Request, call_next):
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

    def actor(request: Request) -> Identity:
        authorization = request.headers.get("authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else None
        identity = identities.authenticate(token)
        if identity is None:
            raise HTTPException(401, "Verified bearer credential required")
        return identity

    def admin(identity: Identity = Depends(actor)) -> Identity:
        if not identity.admin:
            raise HTTPException(403, "Management credential required")
        return identity

    @app.get("/")
    def dashboard():
        return FileResponse(Path(__file__).parent / "web/index.html")

    @app.get("/health")
    def health():
        snapshot = policies.snapshot()
        return {
            "status": "ready",
            "policy_version": snapshot.policy.version,
            "semantic_provider": snapshot.policy.semantic.provider,
            "semantic_status": "disabled"
            if snapshot.policy.semantic.provider == "disabled"
            else "configured; verified per invocation",
        }

    @app.get("/api/me")
    def me(identity: Identity = Depends(actor)):
        return identity

    @app.post("/api/invoke")
    async def invoke(call: ToolCall, identity: Identity = Depends(actor)):
        return await engine.invoke(identity, call)

    @app.post("/api/models/complete")
    async def complete(call: ModelCall, identity: Identity = Depends(actor)):
        return await engine.invoke(identity, call)

    @app.get("/api/admin/status", dependencies=[Depends(admin)])
    def status():
        snapshot = policies.snapshot()
        return {
            "policy": snapshot.policy.model_dump(),
            "feed": snapshot.feed.model_dump(),
            "metrics": ledger.stats(),
            "budgets": ledger.budgets(),
            "audit": ledger.audit(),
            "business_backend": "simulated",
            "budget_window": "UTC day; per trusted subject",
            "semantic_status": "disabled — deterministic controls only"
            if snapshot.policy.semantic.provider == "disabled"
            else "configured — actual model evaluated per invocation; errors fail closed",
        }

    def audit_change(identity: Identity, target: str, reason: str):
        import uuid

        snapshot = policies.snapshot()
        ledger.append(
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

    @app.post("/api/admin/reload")
    def reload_policy(identity: Identity = Depends(admin)):
        try:
            snapshot = policies.reload()
            audit_change(identity, "policy.reload", "policy_reloaded")
            return {
                "policy_version": snapshot.policy.version,
                "feed_version": snapshot.feed.version,
            }
        except Exception:
            raise HTTPException(
                409, "Invalid policy/feed or non-increasing version; last good policy retained"
            ) from None

    @app.put("/api/admin/policy")
    def save_policy(policy: Policy, identity: Identity = Depends(admin)):
        try:
            snapshot = policies.save(policy)
            audit_change(identity, "policy.save", "policy_saved")
            return {"policy_version": snapshot.policy.version}
        except Exception:
            raise HTTPException(409, "Policy not saved; validation/version conflict") from None

    @app.get("/api/admin/audit.jsonl", dependencies=[Depends(admin)])
    def audit_export():
        content = "\n".join(json.dumps(row) for row in reversed(ledger.audit(10_000))) + "\n"
        return Response(
            content,
            media_type="application/x-ndjson",
            headers={"Content-Disposition": 'attachment; filename="fastfence-audit.jsonl"'},
        )

    app.mount("/mcp", mcp_app)
    return app
