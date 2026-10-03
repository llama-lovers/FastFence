import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from fastfence.app.interfaces.http.authoring_process import (
    LayaPolicyAuthor,
    PolicyAuthoringError,
    _local_model_url,
)
from fastfence.shared.settings.app_settings import AppSettings


@pytest.fixture
def worker(tmp_path):
    root = tmp_path / "trusted-installation"
    (root / "state/laya/venv/bin").mkdir(parents=True)
    (root / "state/laya/upstream").mkdir()
    (root / "integrations/laya").mkdir(parents=True)
    (root / "state/laya/venv/bin/python").symlink_to(sys.executable)
    script = root / "integrations/laya/draft_policy.py"
    settings = AppSettings(
        root=tmp_path / "isolated-config", authoring_root=root
    )
    return LayaPolicyAuthor(settings, timeout=0.5), script


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "https://localhost:11434/",
        "http://[::1]:11434",
    ],
)
def test_authoring_accepts_only_local_model_origins(url):
    assert _local_model_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "file:///tmp/private",
        "http://127.0.0.1/path",
        "http://localhost?key=private",
        "http://localhost:invalid",
        "http://localhost/#fragment",
    ],
)
def test_remote_or_nonorigin_model_config_is_rejected(url):
    assert not _local_model_url(url)


async def test_worker_exchange_accumulates_fragmented_output_without_request_log(
    worker,
):
    author, script = worker
    script.write_text(
        "import json,sys,time\n"
        "request=json.load(sys.stdin)\n"
        "sys.stderr.write(request['instruction'])\n"
        "sys.stdout.write('{\"source\":');sys.stdout.flush();time.sleep(.02)\n"
        'sys.stdout.write(\'"real_laya","proposal":{},"inference_ms":1,"model":"qwen3:4b"}\')\n'
    )
    response = await author.draft({"instruction": "private-data-for-worker"})
    assert response["source"] == "real_laya"
    assert "private-data-for-worker" not in json.dumps(response)


@pytest.mark.parametrize(
    "program,code,status",
    [
        ("import time;time.sleep(2)", "laya_authoring_timeout", 504),
        ("print('x'*70000)", "invalid_laya_proposal", 503),
        ("print('private malformed details')", "invalid_laya_proposal", 503),
        (
            'print(\'{"error":"unsupported_or_ambiguous_instruction"}\')',
            "unsupported_or_ambiguous_instruction",
            422,
        ),
        (
            'print(\'{"error":"private provider error"}\')',
            "laya_authoring_failed",
            503,
        ),
    ],
)
async def test_worker_boundaries_fail_with_only_stable_codes(
    worker, program, code, status
):
    author, script = worker
    script.write_text(program)
    with pytest.raises(PolicyAuthoringError) as rejected:
        await author.draft({"instruction": "private request"})
    assert rejected.value.code == code
    assert rejected.value.status == status
    assert not author._slot.locked()


async def test_authoring_busy_slot_rejects_without_second_process(worker):
    author, script = worker
    script.write_text("import time;time.sleep(2)")
    async with author._slot:
        with pytest.raises(
            PolicyAuthoringError, match="authoring_busy_try_again"
        ):
            await author.draft({"instruction": "private request"})


async def test_missing_installation_and_remote_origin_never_spawn(
    tmp_path, monkeypatch
):
    async def forbidden(*args, **kwargs):
        pytest.fail("Invalid trusted configuration spawned a process")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    author = LayaPolicyAuthor(AppSettings(root=tmp_path))
    with pytest.raises(
        PolicyAuthoringError, match="laya_not_installed_run_setup"
    ):
        await author.draft({})


async def test_parent_cleans_private_workspace_when_worker_times_out(
    worker, monkeypatch
):
    author, script = worker
    workspaces = []

    def tracked_directory(**kwargs):
        context = TemporaryDirectory(**kwargs)
        workspaces.append(Path(context.name))
        return context

    monkeypatch.setattr(
        "fastfence.app.interfaces.http.authoring_process.TemporaryDirectory",
        tracked_directory,
    )
    script.write_text(
        "import pathlib,sys,time\n"
        "workspace=pathlib.Path(sys.argv[sys.argv.index('--workspace')+1])\n"
        "(workspace/'private.txt').write_text('private worker data')\n"
        "time.sleep(2)\n"
    )
    with pytest.raises(PolicyAuthoringError, match="laya_authoring_timeout"):
        await author.draft({})
    assert workspaces and all(not path.exists() for path in workspaces)
