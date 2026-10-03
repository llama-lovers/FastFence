"""Specifications must be valid and staged together with covered implementation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.check_specs import uncovered_changes, validate_spec


@pytest.fixture
def specification():
    return {
        "id": "FF-TEST",
        "title": "Specification gate test",
        "status": "implemented",
        "problem": "Implementation requires a reviewable specification.",
        "scope": ["Validate the gate"],
        "constraints": ["Keep changes isolated"],
        "change_paths": ["src/feature/**"],
        "acceptance": ["Uncovered staged implementation fails"],
        "validation": [{"command": "uv run pytest", "expected": "Checks pass"}],
        "evidence": [],
    }


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("id", "bad id"),
        ("status", "approved-without-validation"),
        ("scope", []),
        ("acceptance", [" "]),
        ("validation", []),
        ("unexpected_field", "unchecked"),
    ],
)
def test_invalid_specifications_are_rejected(specification, field, invalid):
    specification[field] = invalid
    with pytest.raises(ValueError, match="specification"):
        validate_spec(yaml.safe_dump(specification), "test.yaml")


def test_verified_specification_requires_evidence(specification):
    specification["status"] = "verified"
    with pytest.raises(ValueError, match="needs evidence"):
        validate_spec(yaml.safe_dump(specification), "test.yaml")
    specification["evidence"] = [{"test_command": "uv run pytest", "passed": 1}]
    assert (
        validate_spec(yaml.safe_dump(specification), "test.yaml").status
        == "verified"
    )


@pytest.mark.parametrize("status", ["implemented", "verified"])
def test_coverage_requires_matching_implementation_paths(specification, status):
    specification["status"] = status
    specification["evidence"] = [{"test_command": "uv run pytest"}]
    validated = validate_spec(yaml.safe_dump(specification), "test.yaml")
    paths = ["src/feature/services/action.py", "src/uncovered.py", "LICENSE"]
    assert uncovered_changes(paths, [validated]) == [
        "src/uncovered.py",
        "LICENSE",
    ]


def test_planned_specification_cannot_authorize_implementation(specification):
    specification["status"] = "planned"
    validated = validate_spec(yaml.safe_dump(specification), "test.yaml")
    assert uncovered_changes(["src/feature/action.py"], [validated]) == [
        "src/feature/action.py"
    ]


def test_real_staged_gate_rejects_unstaged_and_planned_specs(
    tmp_path, specification
):
    script = Path(__file__).resolve().parents[2] / "scripts/check_specs.py"
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "specs").mkdir()
    (tmp_path / "src/feature").mkdir(parents=True)
    (tmp_path / "src/feature/action.py").write_text("VALUE = 1\n")
    spec_path = tmp_path / "specs/change.yaml"
    spec_path.write_text(yaml.safe_dump(specification))
    subprocess.run(["git", "add", "src/"], cwd=tmp_path, check=True)

    def run_gate():
        return subprocess.run(
            [sys.executable, str(script)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

    unstaged = run_gate()
    assert (
        unstaged.returncode != 0 and "src/feature/action.py" in unstaged.stderr
    )
    specification["status"] = "planned"
    spec_path.write_text(yaml.safe_dump(specification))
    subprocess.run(
        ["git", "add", "specs/change.yaml"], cwd=tmp_path, check=True
    )
    assert run_gate().returncode != 0
    specification["status"] = "implemented"
    spec_path.write_text(yaml.safe_dump(specification))
    subprocess.run(
        ["git", "add", "specs/change.yaml"], cwd=tmp_path, check=True
    )
    covered = run_gate()
    assert covered.returncode == 0, covered.stderr
    assert "Specification gate passed" in covered.stdout


@pytest.mark.parametrize(
    "path",
    [
        "Dockerfile",
        ".github/workflows/ci.yml",
        "startup.py",
        "docs/architecture.md",
        "assets/cover.svg",
        "specs/bootstrap.py",
        "specs/ci.sh",
    ],
)
def test_arbitrary_staged_paths_require_matching_specification(
    specification, path
):
    validated = validate_spec(yaml.safe_dump(specification), "test.yaml")
    assert uncovered_changes([path], [validated]) == [path]
    specification["change_paths"] = [path]
    covered = validate_spec(yaml.safe_dump(specification), "test.yaml")
    assert uncovered_changes([path], [covered]) == []


def test_specification_updates_do_not_require_another_specification():
    assert uncovered_changes(["specs/changes/change.yaml"], []) == []


def test_committed_gate_detects_uncovered_files_with_empty_index(
    tmp_path, specification
):
    script = Path(__file__).resolve().parents[2] / "scripts/check_specs.py"

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.org",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            cwd=tmp_path,
            text=True,
        ).strip()

    git("init", "--quiet")
    (tmp_path / "specs").mkdir()
    spec = tmp_path / "specs/change.yaml"
    spec.write_text(yaml.safe_dump(specification))
    git("add", ".")
    git("commit", "-qm", "baseline")
    base = git("rev-parse", "HEAD")
    (tmp_path / "uncovered.py").write_text("VALUE = 1\n")
    git("add", ".")
    git("commit", "-qm", "uncovered")
    result = subprocess.run(
        [sys.executable, str(script), "--base", base],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and "uncovered.py" in result.stderr
    specification["change_paths"] = ["uncovered.py"]
    spec.write_text(yaml.safe_dump(specification))
    git("add", ".")
    git("commit", "-qm", "specification")
    result = subprocess.run(
        [sys.executable, str(script), "--base", base],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("base", ["--help", "HEAD~1", "abc", "A" * 40])
def test_commit_base_rejects_options_and_unresolved_refs(base):
    from scripts.check_specs import changed_paths

    with pytest.raises(ValueError, match="full lowercase commit SHA"):
        changed_paths(base)
