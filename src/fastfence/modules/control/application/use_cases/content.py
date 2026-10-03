"""Inspect or complete a document using one policy snapshot and reservation."""

from collections.abc import Awaitable, Callable

from fastfence.modules.control.application.services.engine import Engine
from fastfence.modules.control.domain.models import Identity, ModelCall, Verdict


class ContentUseCases:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def model(self, identity: Identity, requested: str | None) -> str:
        if requested is not None:
            return requested
        policy = self.engine.policies.snapshot().policy
        return next(
            (
                name
                for name, rule in policy.models.items()
                if set(identity.roles).intersection(rule.roles)
            ),
            "unavailable",
        )

    async def prepare(
        self, identity: Identity, markdown: str, model: str | None
    ) -> Verdict:
        return await self.engine.invoke(
            identity,
            ModelCall(
                model=self.model(identity, model),
                prompt=markdown,
                max_output_tokens=1,
            ),
            inspect_only=True,
        )

    async def complete(
        self,
        identity: Identity,
        markdown: str,
        model: str | None,
        max_output_tokens: int,
        restore_originals: bool,
    ) -> tuple[Verdict, str | None]:
        captured: list[str] = []
        verdict = await self.engine.invoke(
            identity,
            ModelCall(
                model=self.model(identity, model),
                prompt=markdown,
                max_output_tokens=max_output_tokens,
                restore_originals=restore_originals,
            ),
            input_sink=lambda payload: captured.append(payload["prompt"]),
        )
        safe = (
            captured[0]
            if captured and verdict.decision in {"allowed", "redacted"}
            else None
        )
        return verdict, safe

    async def process(
        self,
        identity: Identity,
        source: Callable[[], Awaitable[str]],
        timeout_ms: int,
        model: str | None,
        complete: bool,
        max_output_tokens: int,
        restore_originals: bool,
    ) -> tuple[Verdict, str | None]:
        captured: list[str] = []
        verdict = await self.engine.invoke(
            identity,
            ModelCall(
                model=self.model(identity, model),
                prompt="",
                max_output_tokens=max_output_tokens if complete else 1,
                restore_originals=restore_originals,
            ),
            inspect_only=not complete,
            input_sink=lambda payload: captured.append(payload["prompt"]),
            prompt_source=source,
            preparation_timeout_ms=timeout_ms,
        )
        safe = (
            captured[0]
            if captured and verdict.decision in {"allowed", "redacted"}
            else None
        )
        return verdict, safe
