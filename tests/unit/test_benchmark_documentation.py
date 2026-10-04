"""The downloadable benchmark runs without a checkout and publishes exact source."""

import io
import json
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_archive_is_source_identical_and_launcher_runs_outside_checkout(
    tmp_path,
):
    hook = runpy.run_path(str(ROOT / "scripts/docs_reference.py"))
    content = hook["benchmark_download"]()
    assert content == hook["benchmark_download"]()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert set(archive.namelist()) == set(hook["BENCHMARK_FILES"])
        assert len(archive.namelist()) == 7
        for name in archive.namelist():
            assert not Path(name).is_absolute()
            assert ".." not in Path(name).parts
            assert "state" not in Path(name).parts
            assert archive.read(name) == (ROOT / name).read_bytes()
        archive.extractall(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "scripts/benchmark_package.py"),
            "--help",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "--pypi-version" in result.stdout
    assert "--semantic" in result.stdout


def test_benchmarks_are_in_both_llm_corpora():
    hook = runpy.run_path(str(ROOT / "scripts/docs_reference.py"))
    for language in ("en", "pl"):
        index, full = hook["llm_documents"](
            "https://fastfence.dev", language, hook["endpoint_reference"]()
        )
        assert "/benchmarks/" in index
        assert "--pypi-version 1.0.2" in full
        assert "0.131875" in full
        assert "fastfence-benchmarks.zip" in full


def test_current_documented_figures_match_raw_package_reports():
    for kind in ("deterministic", "semantic"):
        report = json.loads(
            (
                ROOT / f"evaluation/results/installed-package-1.0.2-{kind}.json"
            ).read_text()
        )
        assert report["package"]["version"] == "1.0.2"
        assert report["installation"]["source"] == "public_pypi"
        for suffix in ("", ".pl"):
            page = (ROOT / f"docs/benchmarks{suffix}.md").read_text()
            for row in report["results"]:
                assert f"{row['p50_ms']:.6f}" in page
                assert f"{row['p95_ms']:.6f}" in page
                assert f"{row['throughput_requests_per_second']:.2f}" in page


def test_three_mode_comparison_uses_actual_serial_allowed_measurements():
    report = json.loads(
        (
            ROOT / "evaluation/results/installed-package-1.0.2-comparison.json"
        ).read_text()
    )
    semantic = json.loads(
        (
            ROOT / "evaluation/results/installed-package-1.0.2-semantic.json"
        ).read_text()
    )
    rows = [
        row
        for row in report["results"]
        if row["concurrency"] == 1 and row["workload"] == "allowed_business"
    ]
    rows.append(semantic["results"][0])
    assert len(rows) == 3
    for suffix in ("", ".pl"):
        page = (ROOT / f"docs/benchmarks{suffix}.md").read_text()
        for row in rows:
            for metric in ("p50_ms", "p95_ms", "p99_ms"):
                assert f"{row[metric]:.6f}" in page
