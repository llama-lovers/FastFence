"""Fixed-path management-only storage; runtime enforcement never loads test cases."""

import difflib
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.policy_tests import GeneratedPolicyTest
from fastfence.shared.models import StrictModel


class SavedRegressionSuite(StrictModel):
    schema_version: Literal[1] = 1
    policy_version: int = Field(ge=1)
    policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    feed_version: int = Field(ge=1)
    tests: tuple[GeneratedPolicyTest, ...] = Field(max_length=8)
    scope: str = "Reviewed synthetic local-content cases; no authorization, budget or semantic coverage"


def policy_digest(policy: Policy) -> str:
    canonical = json.dumps(
        policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def yaml_diff(base: Policy, candidate: Policy) -> str:
    return "\n".join(
        difflib.unified_diff(
            yaml.safe_dump(
                base.model_dump(mode="json"), sort_keys=False
            ).splitlines(),
            yaml.safe_dump(
                candidate.model_dump(mode="json"), sort_keys=False
            ).splitlines(),
            fromfile="base-policy.yaml",
            tofile="candidate-policy.yaml",
            lineterm="",
        )
    )


def save_reviewed_tests(path: Path, suite: SavedRegressionSuite) -> None:
    content = yaml.safe_dump(suite.model_dump(mode="json"), sort_keys=False)
    if len(content.encode("utf-8")) > 65_536:
        raise OSError("Regression suite too large")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".policy-tests-", suffix=".yaml.tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)
