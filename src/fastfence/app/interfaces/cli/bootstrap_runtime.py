"""Provision only the active semantic assessor, independently of business models."""

import asyncio
import json

import httpx

from fastfence.app.interfaces.cli.laya_install import setup_laya, stage_laya
from fastfence.app.interfaces.cli.startup import _laya_ready
from fastfence.modules.control.application.facade import build_runtime
from fastfence.shared.settings.app_settings import AppSettings
from fastfence.workflows.anonymization import build_anonymization


async def response_json(
    client: httpx.AsyncClient, method: str, url: str, **kwargs
):
    async with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        content = bytearray()
        async for chunk in response.aiter_bytes():
            if len(content) + len(chunk) > 1_048_576:
                raise ValueError("Ollama response exceeds initialization limit")
            content.extend(chunk)
    return json.loads(content)


async def model_names(client: httpx.AsyncClient, url: str) -> set[str]:
    async with asyncio.timeout(5):
        payload = await response_json(client, "GET", url + "/api/tags")
    models = payload["models"]
    if not isinstance(models, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("name"), str)
        for item in models
    ):
        raise ValueError("Invalid model inventory")
    return {item["name"] for item in models}


async def ensure_assessor(settings: AppSettings, model: str) -> None:
    url = settings.ollama_url.rstrip("/")
    try:
        async with (
            asyncio.timeout(900),
            httpx.AsyncClient(
                timeout=httpx.Timeout(900, connect=3),
                trust_env=False,
                follow_redirects=False,
            ) as client,
        ):
            if model in await model_names(client, url):
                print(
                    "Configured semantic assessor model is already available."
                )
                return
            print(
                "Downloading the configured semantic assessor model; this may take several minutes.",
                flush=True,
            )
            result = await response_json(
                client,
                "POST",
                url + "/api/pull",
                json={"model": model, "stream": False},
            )
            if result.get(
                "status"
            ) != "success" or model not in await model_names(client, url):
                raise ValueError("Assessor installation was not confirmed")
    except (
        httpx.HTTPError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ):
        raise SystemExit(
            "Semantic assessor setup failed. Start Ollama (`ollama serve`) or check FASTFENCE_OLLAMA_URL, then rerun `fastfence init`. "
            "Existing configuration, credentials and keys were preserved; provider response details are omitted."
        ) from None


def initialize_runtime(settings: AppSettings) -> None:
    runtime = build_runtime(
        settings, anonymization=build_anonymization(settings)
    )
    try:
        semantic = runtime.snapshot().policy.semantic
    finally:
        runtime.close()
    if semantic.provider not in {"laya", "ollama"}:
        print(
            "Existing policy preserved; it does not require a local Laya/Ollama assessor."
        )
        return
    asyncio.run(ensure_assessor(settings, semantic.model))
    if semantic.provider == "laya":
        root = settings.authoring_root or settings.root
        try:
            stage_laya(root)
        except ValueError as error:
            raise SystemExit(str(error)) from None
        if _laya_ready(settings):
            print("Laya semantic runtime is already installed.")
        else:
            print("Installing the pinned Laya semantic runtime.", flush=True)
            setup_laya(root)
            if not _laya_ready(settings):
                raise SystemExit(
                    "Laya runtime validation failed; rerun `fastfence setup-laya` and `fastfence init`."
                )
    print(
        "Required semantic components are ready. Start `fastfence serve`. "
        "Business model providers are configured independently."
    )
