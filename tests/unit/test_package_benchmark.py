"""Meaningful benchmark isolation, accounting and warmup contracts."""

import argparse
import importlib
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = runpy.run_path(str(ROOT / "scripts/benchmark_package.py"))
BENCHMARK = importlib.import_module("evaluation.benchmark_gateway")


def test_bundle_stages_only_explicit_fixtures_and_never_runtime_source(
    tmp_path,
):
    checksums = LAUNCHER["stage_bundle"](ROOT, tmp_path)
    assert set(checksums) == set(LAUNCHER["BUNDLE_FILES"])
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / ".env").exists()
    assert not (tmp_path / "state").exists()
    assert all(len(value) == 64 for value in checksums.values())


def test_bundle_refuses_fixture_symlink_outside_download(tmp_path):
    source = tmp_path / "bundle"
    source.mkdir()
    target = source / LAUNCHER["BUNDLE_FILES"][0]
    target.parent.mkdir(parents=True)
    external = tmp_path / "external.py"
    external.write_text("private data")
    target.symlink_to(external)
    with pytest.raises(ValueError, match="external path"):
        LAUNCHER["stage_bundle"](source, tmp_path / "staged")


def test_child_environment_cannot_inherit_operator_settings_or_pythonpath(
    monkeypatch,
):
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    monkeypatch.setenv("FASTFENCE_ROOT", "/private/operator")
    monkeypatch.setenv("FASTFENCE_OLLAMA_URL", "https://unexpected.invalid")
    monkeypatch.setenv("HTTP_PROXY", "http://unexpected.invalid")
    environment = LAUNCHER["clean_environment"]()
    assert all(
        key not in environment
        for key in [
            "PYTHONPATH",
            "FASTFENCE_ROOT",
            "FASTFENCE_OLLAMA_URL",
            "HTTP_PROXY",
        ]
    )
    assert environment["PYTHONNOUSERSITE"] == "1"


def test_semantic_concurrency_and_version_constraints_reject_before_install():
    args = argparse.Namespace(
        samples=20,
        warmup=2,
        concurrency=[1, 8],
        semantic=True,
        pypi_version="1.0.2",
        wheel=None,
    )
    with pytest.raises(ValueError, match="concurrency 1"):
        LAUNCHER["validate"](args)
    args.concurrency = [1]
    args.pypi_version = "latest"
    with pytest.raises(ValueError, match="exact stable"):
        LAUNCHER["validate"](args)


def test_editable_checkout_cannot_be_reported_as_installed_package():
    with pytest.raises(AssertionError, match="installed distribution"):
        BENCHMARK.installed_provenance(ROOT)


@pytest.mark.parametrize("workload", BENCHMARK.WORKLOADS)
@pytest.mark.asyncio
async def test_real_core_counts_warmups_and_verifies_every_verdict(
    tmp_path, workload
):
    BENCHMARK.prepare_configuration(tmp_path, 5, 2, 2)
    report = await BENCHMARK.run_workload(
        tmp_path, workload, 5, 2, 2, "zero_wait_fixture"
    )
    assert report["samples"] == 5
    assert report["warmup_excluded_from_timing"] == 2
    assert report["instance_metrics_including_warmup"]["requests"] == 7
    assert report["semantic_calls_including_warmup"] == 0
    assert report["all_verdicts_verified"] and report["accounting_verified"]
    assert sum(report["outcomes"].values()) == 5
    assert report["p50_ms"] <= report["p95_ms"] <= report["p99_ms"]
    assert report["throughput_requests_per_second"] > 0


def test_semantic_fixture_uses_installed_package_default(tmp_path):
    import yaml

    BENCHMARK.prepare_configuration(tmp_path, 20, 2, 1, semantic=True)
    policy = yaml.safe_load((tmp_path / "policy.yaml").read_text())
    assert policy["semantic"]["provider"] == "laya"
    assert policy["semantic"]["model"] == BENCHMARK.default_semantic()["model"]
    assert policy["semantic"]["scan_output"] is True


@pytest.mark.asyncio
async def test_off_baseline_uses_same_allowed_fixture_without_engine(
    monkeypatch,
):
    def forbidden_engine(*args, **kwargs):
        raise AssertionError("OFF must not initialize FastFence controls")

    monkeypatch.setattr(BENCHMARK, "engine_for", forbidden_engine)
    result = await BENCHMARK.run_unprotected(5, 2, 2)
    assert result["control_mode"] == "off"
    assert result["workload"] == BENCHMARK.WORKLOADS[0].name
    assert result["output_verified"]
    assert result["samples"] == 5 and result["warmup_excluded_from_timing"] == 2
    assert result["semantic_calls_including_warmup"] == 0
    assert result["p50_ms"] <= result["p95_ms"] <= result["p99_ms"]
