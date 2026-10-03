"""Validate YAML specifications and require staged specs for staged implementation."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ValidationStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class ChangeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Z][A-Z0-9-]+$")
    title: str = Field(min_length=1)
    status: Literal["planned", "implemented", "verified"]
    problem: str = Field(min_length=1)
    scope: list[str] = Field(min_length=1)
    constraints: list[str] = Field(min_length=1)
    change_paths: list[str]
    acceptance: list[str] = Field(min_length=1)
    validation: list[ValidationStep] = Field(min_length=1)
    evidence: list[dict[str, str | int | float]]


def validate_spec(text: str, path: str) -> ChangeSpec:
    try:
        spec = ChangeSpec.model_validate(yaml.safe_load(text))
    except (ValidationError, yaml.YAMLError) as error:
        raise ValueError(f"Invalid specification {path}: {error}") from error
    collections = [
        spec.scope,
        spec.constraints,
        spec.change_paths,
        spec.acceptance,
    ]
    if any(not entry.strip() for entries in collections for entry in entries):
        raise ValueError(f"Empty specification entry in {path}")
    if spec.status == "verified" and not spec.evidence:
        raise ValueError(f"Verified specification needs evidence: {path}")
    return spec


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)


def uncovered_changes(paths: list[str], specs: list[ChangeSpec]) -> list[str]:
    patterns = [
        pattern
        for spec in specs
        if spec.status != "planned"
        for pattern in spec.change_paths
    ]
    # New deployment files, root-level scripts and assets need specs too.
    # An enumerated source-root allowlist would let newly added paths bypass the gate.
    implementation = [
        path
        for path in paths
        if not (path.startswith("specs/") and path.endswith(".yaml"))
    ]
    return [
        path
        for path in implementation
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
    ]


def main() -> None:
    paths = sorted(Path("specs").rglob("*.yaml"))
    if not paths:
        raise SystemExit("No project specifications found under specs/")
    specs = [validate_spec(path.read_text(), str(path)) for path in paths]
    ids = [spec.id for spec in specs]
    if len(ids) != len(set(ids)):
        raise SystemExit("Specification IDs must be unique")
    staged = [
        path
        for path in git(
            "diff", "--cached", "--name-only", "--no-renames", "-z"
        ).split("\0")
        if path
    ]
    staged_specs = []
    for path in staged:
        if path.startswith("specs/") and path.endswith(".yaml"):
            staged_text = subprocess.run(
                ["git", "show", f":{path}"],
                text=True,
                capture_output=True,
                check=False,
            )
            if staged_text.returncode == 0:
                staged_specs.append(validate_spec(staged_text.stdout, path))
    missing = uncovered_changes(staged, staged_specs)
    if missing:
        raise SystemExit(
            "Implementation changes require a staged implemented/verified "
            "specification covering these paths:\n" + "\n".join(missing)
        )
    print(
        f"Specification gate passed: {len(specs)} valid specs; {len(staged)} staged paths"
    )


if __name__ == "__main__":
    main()
