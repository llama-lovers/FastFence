"""Bounded isolated admin-plane adapter for the actual pinned Laya client."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlsplit

from fastfence.shared.settings.app_settings import AppSettings


class PolicyAuthoringError(Exception):
    def __init__(self, code: str, status: int = 422) -> None:
        self.code, self.status = code, status
        super().__init__(code)


def _local_model_url(value: str) -> bool:
    import ipaddress

    parts = urlsplit(value)
    try:
        local = (
            parts.hostname == "localhost"
            or ipaddress.ip_address(parts.hostname or "").is_loopback
        )
        _ = parts.port
    except ValueError:
        return False
    return bool(
        local
        and parts.scheme in {"http", "https"}
        and parts.path in {"", "/"}
        and not parts.username
        and not parts.password
        and not parts.query
        and not parts.fragment
    )


class LayaPolicyAuthor:
    model = "qwen3:4b"

    def __init__(self, settings: AppSettings, timeout: float = 75.0) -> None:
        self.settings, self.timeout = settings, timeout
        self._slot = asyncio.Lock()

    async def draft(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._slot.locked():
            raise PolicyAuthoringError("authoring_busy_try_again", 429)
        async with self._slot:
            return await self._run(request)

    async def _run(self, request: dict[str, Any]) -> dict[str, Any]:
        settings = self.settings
        root = settings.authoring_root or settings.root
        interpreter = root / "state/laya/venv/bin/python"
        script = root / "integrations/laya/draft_policy.py"
        source = root / "state/laya/upstream"
        if not all(path.exists() for path in (interpreter, script, source)):
            raise PolicyAuthoringError("laya_not_installed_run_setup", 503)
        if not _local_model_url(settings.ollama_url):
            raise PolicyAuthoringError("authoring_requires_local_model", 503)
        # Parent owns cleanup even when timeout kills the Laya process.
        with TemporaryDirectory(prefix="fastfence-policy-author-") as workspace:
            return await self._invoke(
                interpreter, script, source, Path(workspace), request
            )

    async def _invoke(
        self,
        interpreter: Path,
        script: Path,
        source: Path,
        workspace: Path,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            str(interpreter),
            str(script),
            "--source",
            str(source),
            "--ollama-url",
            self.settings.ollama_url,
            "--model",
            self.model,
            "--workspace",
            str(workspace),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=65_536,
        )
        try:
            data = await asyncio.wait_for(
                self._exchange(process, request), timeout=self.timeout
            )
            response = json.loads(data)
            if not isinstance(response, dict):
                raise ValueError("Invalid worker response")
            if response.get("error") == "unsupported_or_ambiguous_instruction":
                raise PolicyAuthoringError(
                    "unsupported_or_ambiguous_instruction"
                )
            if process.returncode or "error" in response:
                raise PolicyAuthoringError("laya_authoring_failed", 503)
            return response
        except TimeoutError:
            raise PolicyAuthoringError("laya_authoring_timeout", 504) from None
        except (ValueError, OSError):
            raise PolicyAuthoringError("invalid_laya_proposal", 503) from None
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()

    @staticmethod
    async def _exchange(
        process: asyncio.subprocess.Process, request: dict[str, Any]
    ) -> bytes:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(request, ensure_ascii=False).encode())
        await process.stdin.drain()
        process.stdin.close()
        chunks, size = [], 0
        while chunk := await process.stdout.read(4096):
            size += len(chunk)
            if size > 65_536:
                raise ValueError("Worker output too large")
            chunks.append(chunk)
        await process.wait()
        return b"".join(chunks)
