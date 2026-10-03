"""No-argument startup provisions private state before serving, or fails closed."""

import json
import os
from unittest.mock import Mock

import pytest
import yaml

from fastfence.app.interfaces.cli import bootstrap_ocr, startup
from fastfence.app.interfaces.cli import main as cli
from fastfence.shared.settings.app_settings import AppSettings


def invoke(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["fastfence", *args])
    cli.main()


def isolate(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("FASTFENCE_ROOT", str(root))
    monkeypatch.delenv("FASTFENCE_STATE", raising=False)


def test_no_command_creates_private_state_then_prepares_components_then_serves(
    tmp_path, monkeypatch, capsys
):
    isolate(monkeypatch, tmp_path)
    events = []

    def semantic(settings):
        assert (settings.root / "config/policy.yaml").is_file()
        assert (settings.state_path / "credentials.json").is_file()
        assert (settings.state_path / "anonymization-keys.json").is_file()
        events.append("semantic")

    def ocr(settings):
        events.append("ocr")
        return settings

    monkeypatch.setattr(cli, "initialize_runtime", semantic)
    monkeypatch.setattr(cli, "ensure_ocr", ocr)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **kw: events.append(kw))
    invoke(monkeypatch)
    assert events[:2] == ["semantic", "ocr"]
    assert events[2] == {"factory": True, "host": "127.0.0.1", "port": 8000}
    credentials = json.loads((tmp_path / "state/credentials.json").read_text())
    output = capsys.readouterr().out
    assert "FastFence dashboard: http://127.0.0.1:8000" in output
    assert all(token not in output for token in credentials.values())


def test_repeat_no_command_preserves_existing_policy_credentials_and_keys(
    tmp_path, monkeypatch
):
    isolate(monkeypatch, tmp_path)
    invoke(monkeypatch, "init", "--config-only")
    policy = tmp_path / "config/policy.yaml"
    content = yaml.safe_load(policy.read_text())
    content.update(version=7, description="Operator's existing policy")
    policy.write_text(yaml.safe_dump(content))
    paths = [policy, *(tmp_path / "state").glob("*.json")]
    before = {path: path.read_bytes() for path in paths}
    monkeypatch.setattr(cli, "initialize_runtime", Mock())
    monkeypatch.setattr(cli, "ensure_ocr", lambda settings: settings)
    server = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", server)
    invoke(monkeypatch)
    invoke(monkeypatch)
    assert {path: path.read_bytes() for path in paths} == before
    assert server.call_count == 2


def test_no_command_honors_configuration_root_and_explicit_state(
    tmp_path, monkeypatch
):
    working, root = tmp_path / "working", tmp_path / "installation"
    working.mkdir()
    root.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setenv("FASTFENCE_ROOT", str(root))
    monkeypatch.delenv("FASTFENCE_STATE", raising=False)
    state = tmp_path / "private-state"
    monkeypatch.setattr(cli, "initialize_runtime", Mock())
    monkeypatch.setattr(cli, "ensure_ocr", lambda settings: settings)
    server = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", server)
    invoke(monkeypatch, "--state", str(state), "--port", "8002")
    assert (root / "config/policy.yaml").is_file()
    assert (state / "credentials.json").is_file()
    assert not (working / "config").exists()
    assert "FASTFENCE_STATE" not in os.environ
    assert server.call_args.kwargs["port"] == 8002


@pytest.mark.parametrize("failure", ["semantic", "ocr"])
def test_failed_component_preparation_never_starts_server_and_preserves_private_state(
    tmp_path, monkeypatch, failure
):
    isolate(monkeypatch, tmp_path)
    invoke(monkeypatch, "init", "--config-only")
    before = {
        path: path.read_bytes() for path in (tmp_path / "state").glob("*.json")
    }
    monkeypatch.setattr(
        cli,
        "initialize_runtime",
        Mock(
            side_effect=SystemExit("semantic setup failed")
            if failure == "semantic"
            else None
        ),
    )
    monkeypatch.setattr(
        cli, "ensure_ocr", Mock(side_effect=SystemExit("OCR setup failed"))
    )
    server = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", server)
    with pytest.raises(SystemExit, match="setup failed"):
        invoke(monkeypatch)
    server.assert_not_called()
    assert {path: path.read_bytes() for path in before} == before


def test_no_command_rejects_partial_existing_private_state_without_repairing_it(
    tmp_path, monkeypatch
):
    isolate(monkeypatch, tmp_path)
    invoke(monkeypatch, "init", "--config-only")
    credentials = tmp_path / "state/credentials.json"
    original = credentials.read_bytes()
    (tmp_path / "state/identities.json").unlink()
    server = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", server)
    with pytest.raises(SystemExit, match="preserved"):
        invoke(monkeypatch)
    assert credentials.read_bytes() == original
    assert not (tmp_path / "state/identities.json").exists()
    server.assert_not_called()


def test_no_command_config_only_requires_explicit_init(tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    with pytest.raises(SystemExit) as caught:
        invoke(monkeypatch, "--config-only")
    assert caught.value.code == 2
    assert not (tmp_path / "state").exists()


def test_missing_ocr_installs_then_rediscovers_new_interpreter_and_models(
    tmp_path, monkeypatch
):
    isolate(monkeypatch, tmp_path)
    settings = AppSettings.environment()
    checks = iter([False, True])
    monkeypatch.setattr(bootstrap_ocr, "_ocr_ready", lambda _: next(checks))

    def install(state):
        interpreter = state / "private/ocr-env/bin/python"
        interpreter.parent.mkdir(parents=True)
        interpreter.touch()
        (state / "private/ocr-models").mkdir()

    monkeypatch.setattr(bootstrap_ocr, "setup_ocr", install)
    result = bootstrap_ocr.ensure_ocr(settings)
    assert result.ocr_python == tmp_path / "state/private/ocr-env/bin/python"
    assert result.ocr_models == tmp_path / "state/private/ocr-models"
    assert settings.ocr_python is None


def test_existing_ocr_is_not_reinstalled(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap_ocr, "_ocr_ready", lambda _: True)
    install = Mock()
    monkeypatch.setattr(bootstrap_ocr, "setup_ocr", install)
    settings = AppSettings(root=tmp_path)
    assert bootstrap_ocr.ensure_ocr(settings) is settings
    install.assert_not_called()


def test_custom_unavailable_ocr_path_is_not_silently_replaced(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(bootstrap_ocr, "_ocr_ready", lambda _: False)
    install = Mock()
    monkeypatch.setattr(bootstrap_ocr, "setup_ocr", install)
    settings = AppSettings(root=tmp_path, ocr_python=tmp_path / "custom/python")
    with pytest.raises(SystemExit, match="Custom runtime paths were preserved"):
        bootstrap_ocr.ensure_ocr(settings)
    install.assert_not_called()
    assert settings.ocr_python == tmp_path / "custom/python"


def test_incomplete_ocr_installation_fails_validation(tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(bootstrap_ocr, "_ocr_ready", lambda _: False)
    monkeypatch.setattr(bootstrap_ocr, "setup_ocr", Mock())
    with pytest.raises(SystemExit, match="did not produce a usable runtime"):
        bootstrap_ocr.ensure_ocr(AppSettings.environment())


@pytest.mark.parametrize("source", ["file", "json"])
def test_external_identity_source_preserved_without_local_credentials(
    tmp_path, monkeypatch, source
):
    isolate(monkeypatch, tmp_path)
    external = tmp_path / "external"
    cli.initialize(external)
    identity_file = external / "identities.json"
    if source == "file":
        monkeypatch.setenv("FASTFENCE_IDENTITY_CONFIG_FILE", str(identity_file))
    else:
        monkeypatch.setenv(
            "FASTFENCE_IDENTITY_CONFIG_JSON", identity_file.read_text()
        )
    state = tmp_path / "state"
    state.mkdir()
    orphan = state / "credentials.json"
    orphan.write_text("unrelated preserved file")
    original = {path: path.read_bytes() for path in external.iterdir()}
    monkeypatch.setattr(cli, "initialize_runtime", Mock())
    monkeypatch.setattr(cli, "ensure_ocr", lambda settings: settings)
    server = Mock()
    monkeypatch.setattr(cli.uvicorn, "run", server)
    invoke(monkeypatch)
    assert orphan.read_text() == "unrelated preserved file"
    assert not (state / "identities.json").exists()
    assert {path: path.read_bytes() for path in original} == original
    server.assert_called_once()


def test_invalid_external_identity_fails_before_component_downloads(
    tmp_path, monkeypatch
):
    isolate(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "FASTFENCE_IDENTITY_CONFIG_JSON", "invalid-private-identity"
    )
    installer, server = Mock(), Mock()
    monkeypatch.setattr(cli, "initialize_runtime", installer)
    monkeypatch.setattr(cli.uvicorn, "run", server)
    with pytest.raises(SystemExit, match="validation input is omitted"):
        invoke(monkeypatch)
    installer.assert_not_called()
    server.assert_not_called()
    assert not (tmp_path / "state/credentials.json").exists()


@pytest.mark.parametrize("weight_state", ["missing", "empty", "complete"])
def test_ocr_readiness_requires_nonempty_model_weights(
    tmp_path, monkeypatch, weight_state
):
    models = tmp_path / "models"
    names = (
        "PP-LCNet_x1_0_doc_ori",
        "PP-OCRv5_mobile_det",
        "latin_PP-OCRv5_mobile_rec",
    )
    for name in names:
        directory = models / name
        directory.mkdir(parents=True)
        for filename in (
            "inference.json",
            "inference.pdiparams",
            "inference.yml",
        ):
            (directory / filename).write_bytes(b"synthetic model fixture")
    weights = models / names[-1] / "inference.pdiparams"
    if weight_state == "missing":
        weights.unlink()
    elif weight_state == "empty":
        weights.write_bytes(b"")
    imports = Mock(return_value=True)
    monkeypatch.setattr(startup, "_python_imports", imports)
    settings = AppSettings(
        root=tmp_path, ocr_python=tmp_path / "python", ocr_models=models
    )
    assert startup._ocr_ready(settings) is (weight_state == "complete")
    assert imports.call_count == (1 if weight_state == "complete" else 0)
