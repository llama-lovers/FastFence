"""Cold-start contracts use real settings and private files in an isolated root."""

import json
import os
from pathlib import Path

import pytest

from fastfence.app.interfaces.cli import main as cli
from fastfence.app.interfaces.cli.initialize import initialize, initialize_keys
from fastfence.app.interfaces.cli.startup import doctor, preflight
from fastfence.shared.settings.app_settings import AppSettings


def run_cli(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["fastfence", *args])
    cli.main()


def test_clean_serve_has_actionable_error_and_never_bootstraps(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FASTFENCE_STATE", raising=False)
    with pytest.raises(SystemExit, match="fastfence init"):
        run_cli(monkeypatch, "serve")
    assert not (tmp_path / "state").exists()


def test_repeat_init_preserves_credentials_and_keys(tmp_path, capsys):
    state = tmp_path / "private"
    initialize(state)
    initialize_keys(state / "anonymization-keys.json", "local-v1")
    before = {file.name: file.read_bytes() for file in state.iterdir()}
    initialize(state)
    initialize_keys(state / "anonymization-keys.json", "local-v1")
    assert before == {file.name: file.read_bytes() for file in state.iterdir()}
    assert all(file.stat().st_mode & 0o777 == 0o600 for file in state.iterdir())
    output = capsys.readouterr().out
    for token in json.loads(before["credentials.json"]).values():
        assert token not in output
    for key in json.loads(before["anonymization-keys.json"]).values():
        assert key not in output


@pytest.mark.parametrize(
    "kind", ["identities", "tokens", "corrupt", "mismatched"]
)
def test_partial_or_corrupt_init_preserves_files(tmp_path, kind):
    state = tmp_path / "state"
    initialize(state)
    if kind == "identities":
        (state / "credentials.json").unlink()
    elif kind == "tokens":
        (state / "identities.json").unlink()
    elif kind == "corrupt":
        (state / "identities.json").write_text("[]")
    else:
        (state / "credentials.json").write_text('{"someone": "mismatch"}')
    before = {path.name: path.read_bytes() for path in state.iterdir()}
    with pytest.raises(SystemExit, match="preserved"):
        initialize(state)
    assert before == {path.name: path.read_bytes() for path in state.iterdir()}


def test_dotenv_state_is_honored_and_explicit_flag_overrides(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FASTFENCE_STATE", raising=False)
    (tmp_path / ".env").write_text("FASTFENCE_STATE=private-state\n")
    run_cli(monkeypatch, "init", "--anonymization")
    assert (tmp_path / "private-state/anonymization-keys.json").is_file()
    assert "FASTFENCE_STATE" not in os.environ
    run_cli(monkeypatch, "init", "--state", "other")
    assert (tmp_path / "other/identities.json").is_file()


def test_serve_preflights_before_uvicorn_and_preserves_dotenv(
    project, monkeypatch
):
    monkeypatch.chdir(project)
    monkeypatch.delenv("FASTFENCE_STATE", raising=False)
    (project / ".env").write_text("FASTFENCE_STATE=state\n")
    called = []
    monkeypatch.setattr(
        cli.uvicorn,
        "run",
        lambda *args, **kwargs: called.append((args, kwargs)),
    )
    run_cli(monkeypatch, "serve")
    assert called[0][1]["factory"] is True
    assert "FASTFENCE_STATE" not in os.environ


def test_invalid_settings_never_echo_private_values(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    private = "do-not-echo-this-private-value"
    monkeypatch.setenv("FASTFENCE_AUDIT_LIMIT", private)
    with pytest.raises(SystemExit) as caught:
        run_cli(monkeypatch, "serve")
    assert "doctor" in str(caught.value)
    assert private not in str(caught.value) + capsys.readouterr().out


def test_preflight_missing_policy_points_to_root(project):
    (project / "config/policy.yaml").unlink()
    with pytest.raises(SystemExit, match="FASTFENCE_ROOT"):
        preflight(AppSettings(root=project))


def test_preflight_invalid_identity_is_sanitized(project, monkeypatch):
    monkeypatch.chdir(project)
    invalid_record = "private-invalid-identity"
    (project / "state/identities.json").write_text(json.dumps([invalid_record]))
    with pytest.raises(SystemExit) as caught:
        run_cli(monkeypatch, "serve")
    assert invalid_record not in str(caught.value)
    assert "configuration failed" in str(caught.value)


def test_doctor_is_read_only(project, capsys):
    before = {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    doctor(AppSettings(root=project))
    after = {
        str(path.relative_to(project)): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert "OK core" in capsys.readouterr().out


def test_doctor_full_reports_optional_failures_without_values(
    project, monkeypatch, capsys
):
    from fastfence.app.interfaces.cli import startup

    for check in ["_ocr_ready", "_laya_ready", "_ollama_ready"]:
        monkeypatch.setattr(startup, check, lambda settings: False)
    with pytest.raises(SystemExit) as caught:
        doctor(AppSettings(root=project), full=True)
    assert caught.value.code == 1
    assert "scripts/setup-ocr.sh" in capsys.readouterr().out


def test_auto_detects_ocr_paths_without_resolving_python_symlink(tmp_path):
    import sys

    state = tmp_path / "state"
    python = state / "private/ocr-env/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    models = state / "private/ocr-models"
    models.mkdir()
    settings = AppSettings(root=tmp_path)
    assert settings.ocr_python == python
    assert settings.ocr_models == models
    explicit = AppSettings(root=tmp_path, ocr_python=Path("/explicit/python"))
    assert explicit.ocr_python == Path("/explicit/python")


def test_init_anonymization_preserves_valid_environment_keyring(
    tmp_path, monkeypatch, capsys
):
    import base64

    monkeypatch.chdir(tmp_path)
    encoded = base64.b64encode(bytes(range(32))).decode()
    monkeypatch.setenv(
        "FASTFENCE_ANONYMIZATION_KEYS_JSON", json.dumps({"local-v1": encoded})
    )
    run_cli(monkeypatch, "init", "--anonymization")
    assert not (tmp_path / "state/anonymization-keys.json").exists()
    output = capsys.readouterr().out
    assert "keyring validated and preserved" in output
    assert encoded not in output


@pytest.mark.parametrize("mutation", ["subject", "roles", "duplicate_hash"])
def test_existing_invalid_identity_schema_or_duplicate_hash_is_rejected(
    tmp_path, mutation
):
    state = tmp_path / "state"
    initialize(state)
    records = json.loads((state / "identities.json").read_text())
    tokens = json.loads((state / "credentials.json").read_text())
    if mutation == "subject":
        previous = records[0]["identity"]["subject"]
        records[0]["identity"]["subject"] = "invalid subject"
        tokens["invalid subject"] = tokens.pop(previous)
    elif mutation == "roles":
        records[0]["identity"]["roles"] = [123]
    else:
        records[1]["token_sha256"] = records[0]["token_sha256"]
        tokens[records[1]["identity"]["subject"]] = tokens[
            records[0]["identity"]["subject"]
        ]
    (state / "identities.json").write_text(json.dumps(records))
    (state / "credentials.json").write_text(json.dumps(tokens))
    before = {p.name: p.read_bytes() for p in state.iterdir()}
    with pytest.raises(SystemExit, match="preserved"):
        initialize(state)
    assert before == {p.name: p.read_bytes() for p in state.iterdir()}
