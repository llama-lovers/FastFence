"""Killable local worker: raw document bytes never leave this machine."""

import asyncio
import json
import os
from pathlib import Path

from fastfence.shared.ocr import MediaType, OCRDocument, OCRError, OCRLimits

RESULT_BYTES = 2 * 1024 * 1024


class PaddleOCRProvider:
    def __init__(
        self, python: Path | None, models: Path | None, limits: OCRLimits
    ) -> None:
        self.python, self.models, self.limits = python, models, limits
        self._slot = asyncio.Semaphore(1)

    async def extract(
        self, content: bytes, media_type: MediaType
    ) -> OCRDocument:
        if len(content) > self.limits.max_bytes:
            raise OCRError("ocr_input_limit")
        if self.python is None or self.models is None:
            raise OCRError("ocr_unavailable")
        if self._slot.locked():
            raise OCRError("ocr_busy")
        async with self._slot:
            try:
                async with asyncio.timeout(self.limits.timeout_seconds):
                    return await self._run(content, media_type)
            except TimeoutError:
                raise OCRError("ocr_timeout") from None
            except OCRError:
                raise
            except Exception:
                raise OCRError("ocr_unavailable") from None

    async def _run(self, content: bytes, media_type: MediaType) -> OCRDocument:
        environment = {
            key: os.environ[key]
            for key in ("PATH", "LANG", "LC_ALL", "TMPDIR")
            if key in os.environ
        }
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[4])
        environment["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        environment["OMP_NUM_THREADS"] = "2"
        process = await asyncio.create_subprocess_exec(
            str(self.python),
            "-m",
            "fastfence.modules.ocr.persistence.worker",
            media_type,
            str(self.models),
            self.limits.model_dump_json(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
        )
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(content)
            await process.stdin.drain()
            process.stdin.close()
            output = bytearray()
            while chunk := await process.stdout.read(65_536):
                output.extend(chunk)
                if len(output) > RESULT_BYTES:
                    raise OCRError("ocr_text_limit")
            await process.wait()
            return self._result(bytes(output), process.returncode)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    @staticmethod
    def _result(output: bytes, returncode: int | None) -> OCRDocument:
        try:
            data = json.loads(output)
            if returncode != 0 or "error" in data:
                raise OCRError(data.get("error", "ocr_page_failed"))
            return OCRDocument.model_validate(data)
        except OCRError:
            raise
        except Exception:
            raise OCRError("ocr_invalid_result") from None
