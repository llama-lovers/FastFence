"""Single-flight bounded prerequisite checks; never perform model inference."""

import asyncio
import json
import os
import signal
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fastfence.modules.control.contracts.readiness import ReadinessReport
from fastfence.modules.control.domain.models import SemanticConfig
from fastfence.modules.control.persistence.laya_semantic import local_origin
from fastfence.modules.control.persistence.semantic_severity import (
    unique_fields,
)
from fastfence.shared.settings.upstream_url import validate_openai_base_url

DEADLINE_SECONDS = 5
CACHE_SECONDS = 10
MAX_TAG_BYTES = 1_048_576
INITIALIZE_ONLY = """import asyncio,sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from semantic_worker import initialize
async def check():
    await initialize(Path(sys.argv[2]), sys.argv[3])
    from laya.tasks import cancel_all
    from laya.http_client import close_client
    await cancel_all()
    await close_client()
asyncio.run(check())
"""


def result(config: SemanticConfig, reason: str) -> ReadinessReport:
    return ReadinessReport.model_validate(
        {
            "status": "ready"
            if reason in {"not_required", "prerequisites_checked"}
            else "not_ready",
            "semantic_provider": config.provider,
            "reason": reason,
            "checked_at": datetime.now(UTC),
        }
    )


class SemanticReadiness:
    def __init__(self, root: Path, ollama_url: str) -> None:
        self.root, self.url = root, ollama_url
        self._lock = asyncio.Lock()
        self._cached: tuple[tuple[str, str], float, ReadinessReport] | None = (
            None
        )

    def _lookup(self, key: tuple[str, str]) -> ReadinessReport | None:
        if self._cached is None:
            return None
        cached_key, expires, report = self._cached
        return (
            report if cached_key == key and time.monotonic() < expires else None
        )

    async def check(self, config: SemanticConfig) -> ReadinessReport:
        key = (config.provider, config.model)
        cached = self._lookup(key)
        if cached is not None:
            return cached
        probing = False
        try:
            async with asyncio.timeout(DEADLINE_SECONDS):
                async with self._lock:
                    cached = self._lookup(key)
                    if cached is not None:
                        return cached
                    probing = True
                    report = await self._probe(config)
                    self._cached = (
                        key,
                        time.monotonic() + CACHE_SECONDS,
                        report,
                    )
                    return report
        except TimeoutError:
            report = result(config, "probe_timeout")
            if probing:
                self._cached = (key, time.monotonic() + CACHE_SECONDS, report)
            return report

    async def _probe(self, config: SemanticConfig) -> ReadinessReport:
        try:
            if config.provider == "disabled":
                return result(config, "not_required")
            if config.provider == "kev":
                return result(config, "provider_probe_unsupported")
            if config.provider == "laya":
                if (
                    not local_origin(self.url)
                    or not await self._laya_initialized()
                ):
                    return result(config, "laya_installation_unavailable")
            url = validate_openai_base_url(self.url).rstrip("/")
            if not await self._model_available(url, config.model):
                return result(config, "model_unavailable")
            return result(config, "prerequisites_checked")
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            RecursionError,
            httpx.HTTPError,
        ):
            return result(config, "probe_failed")

    async def _model_available(self, url: str, model: str) -> bool:
        async with httpx.AsyncClient(
            timeout=3, trust_env=False, follow_redirects=False
        ) as client:
            async with client.stream("GET", url + "/api/tags") as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > MAX_TAG_BYTES:
                        raise ValueError(
                            "Model inventory exceeds readiness bound"
                        )
                    content.extend(chunk)
        payload = json.loads(content, object_pairs_hook=unique_fields)
        models = payload["models"]
        if not isinstance(models, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str)
            for item in models
        ):
            raise ValueError("Invalid model inventory")

        def tagged(name: str) -> str:
            return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"

        return any(tagged(item["name"]) == tagged(model) for item in models)

    async def _laya_initialized(self) -> bool:
        interpreter = self.root / "state/laya/venv/bin/python"
        helpers = self.root / "integrations/laya"
        source = self.root / "state/laya/upstream"
        if (
            not interpreter.is_file()
            or not os.access(interpreter, os.X_OK)
            or not all(
                path.is_file()
                for path in (
                    helpers / "semantic_worker.py",
                    helpers / "semantic_response.py",
                    helpers / "authoring_contracts.py",
                    source / "engine/laya/llm/client.py",
                )
            )
        ):
            return False
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "TMPDIR", "LANG", "SYSTEMROOT"}
        }
        environment.update(
            PYTHONDONTWRITEBYTECODE="1",
            LITELLM_LOCAL_MODEL_COST_MAP="True",
            DO_NOT_TRACK="1",
            LITELLM_MODE="PRODUCTION",
            PYTHON_DOTENV_DISABLED="1",
        )
        process = await asyncio.create_subprocess_exec(
            str(interpreter),
            "-I",
            "-B",
            "-c",
            INITIALIZE_ONLY,
            str(helpers),
            str(source),
            self.url,
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            return await process.wait() == 0
        finally:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
