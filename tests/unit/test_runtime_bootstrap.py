"""Default init provisions the semantic runtime without coupling business models."""

import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest
import yaml

from fastfence.app.interfaces.cli import bootstrap_runtime, main, startup
from fastfence.app.interfaces.cli.bootstrap_config import initialize_config
from fastfence.app.interfaces.cli.initialize import initialize, initialize_keys
from fastfence.shared.settings.app_settings import AppSettings


def client_fixture(monkeypatch, handler):
    factory = httpx.AsyncClient
    seen = []

    def create(**kwargs):
        seen.append(kwargs)
        return factory(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(bootstrap_runtime.httpx, "AsyncClient", create)
    return seen


def test_missing_assessor_downloads_only_configured_model(
    monkeypatch, tmp_path
):
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path, request.content))
        if request.method == "POST":
            assert json.loads(request.content) == {
                "model": "qwen3:4b",
                "stream": False,
            }
            return httpx.Response(200, json={"status": "success"})
        names = [] if len(calls) == 1 else [{"name": "qwen3:4b"}]
        return httpx.Response(200, json={"models": names})

    options = client_fixture(monkeypatch, handle)
    asyncio.run(
        bootstrap_runtime.ensure_assessor(
            AppSettings(root=tmp_path), "qwen3:4b"
        )
    )
    assert [call[:2] for call in calls] == [
        ("GET", "/api/tags"),
        ("POST", "/api/pull"),
        ("GET", "/api/tags"),
    ]
    assert options[0]["trust_env"] is False
    assert options[0]["follow_redirects"] is False
    assert "qwen3:0.6b" not in repr(calls)


def test_existing_assessor_skips_download(monkeypatch, tmp_path):
    calls = []

    def handle(request):
        calls.append(request.method)
        return httpx.Response(
            200, json={"models": [{"name": "custom:assessor"}]}
        )

    client_fixture(monkeypatch, handle)
    asyncio.run(
        bootstrap_runtime.ensure_assessor(
            AppSettings(root=tmp_path), "custom:assessor"
        )
    )
    assert calls == ["GET"]


@pytest.mark.parametrize(
    "kind",
    [
        "offline",
        "malformed",
        "oversized",
        "pull_error",
        "missing_after_pull",
        "timeout",
    ],
)
def test_failed_setup_is_bounded_and_never_echoes_provider_payload(
    monkeypatch, tmp_path, kind, capsys
):
    private = "private-provider-diagnostic"

    def handle(request):
        if kind == "offline":
            raise httpx.ConnectError(private, request=request)
        if kind == "timeout":
            raise TimeoutError(private)
        if kind == "malformed":
            return httpx.Response(200, text=private)
        if kind == "oversized":
            return httpx.Response(200, content=b"x" * 1_048_577)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"status": private if kind == "pull_error" else "success"},
            )
        return httpx.Response(200, json={"models": []})

    client_fixture(monkeypatch, handle)
    with pytest.raises(SystemExit, match="rerun `fastfence init`") as caught:
        asyncio.run(
            bootstrap_runtime.ensure_assessor(
                AppSettings(root=tmp_path), "configured:assessor"
            )
        )
    assert private not in str(caught.value) + capsys.readouterr().out


def test_init_config_only_never_calls_runtime_and_preserves_state(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FASTFENCE_ROOT", str(tmp_path))
    runtime = Mock(side_effect=AssertionError("network bootstrap forbidden"))
    monkeypatch.setattr(main, "initialize_runtime", runtime)
    monkeypatch.setattr("sys.argv", ["fastfence", "init", "--config-only"])
    main.main()
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    main.main()
    assert before == {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert (tmp_path / "state/anonymization-keys.json").is_file()
    runtime.assert_not_called()


def test_default_init_invokes_runtime_after_local_provisioning(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FASTFENCE_ROOT", str(tmp_path))
    ready = []

    def provision(settings):
        assert (settings.root / "config/policy.yaml").is_file()
        assert (settings.state_path / "credentials.json").is_file()
        assert (settings.state_path / "anonymization-keys.json").is_file()
        ready.append(settings.root)

    monkeypatch.setattr(main, "initialize_runtime", provision)
    monkeypatch.setattr("sys.argv", ["fastfence", "init"])
    main.main()
    assert ready == [tmp_path]


def runtime_root(tmp_path, provider):
    initialize_config(tmp_path)
    initialize(tmp_path / "state")
    initialize_keys(tmp_path / "state/anonymization-keys.json", "local-v1")
    path = tmp_path / "config/policy.yaml"
    policy = yaml.safe_load(path.read_text())
    policy["semantic"].update(provider=provider, model="configured:assessor")
    path.write_text(yaml.safe_dump(policy))
    return AppSettings(root=tmp_path), path


@pytest.mark.parametrize("installed", [False, True])
def test_laya_setup_only_when_needed_without_policy_rewrite(
    monkeypatch, tmp_path, installed
):
    settings, path = runtime_root(tmp_path, "laya")
    before = path.read_bytes()
    assessor = []

    async def ensure(settings, model):
        assessor.append(model)

    monkeypatch.setattr(bootstrap_runtime, "ensure_assessor", ensure)
    monkeypatch.setattr(bootstrap_runtime, "stage_laya", Mock())
    checks = iter([installed, True])
    monkeypatch.setattr(
        bootstrap_runtime, "_laya_ready", lambda _: next(checks)
    )
    install = Mock()
    monkeypatch.setattr(bootstrap_runtime, "setup_laya", install)
    bootstrap_runtime.initialize_runtime(settings)
    assert assessor == ["configured:assessor"]
    assert install.call_count == (0 if installed else 1)
    assert path.read_bytes() == before


def test_disabled_existing_policy_needs_no_laya_or_model(monkeypatch, tmp_path):
    settings, path = runtime_root(tmp_path, "disabled")
    before = path.read_bytes()
    for name in ("ensure_assessor", "stage_laya", "setup_laya"):
        monkeypatch.setattr(
            bootstrap_runtime,
            name,
            Mock(side_effect=AssertionError("must not provision")),
        )
    bootstrap_runtime.initialize_runtime(settings)
    assert path.read_bytes() == before


def test_doctor_assessor_inventory_ignores_business_model(
    monkeypatch, tmp_path
):
    settings, _ = runtime_root(tmp_path, "laya")
    factory = httpx.Client
    monkeypatch.setattr(
        startup.httpx,
        "Client",
        lambda **kwargs: factory(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"models": [{"name": "configured:assessor"}]}
                )
            ),
            **kwargs,
        ),
    )
    assert startup._ollama_ready(settings)
