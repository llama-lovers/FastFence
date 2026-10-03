"""Lossless generation envelope adapter; rule and expectation values are unchanged."""

from copy import deepcopy
from typing import Any

from authoring_contracts import AuthoringError

CASE_KEYS = tuple(f"case-{index}" for index in range(1, 5))


def generation_schema(schema: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(schema)
    case = deepcopy(prepared["$defs"]["GeneratedPolicyTest"])
    case["properties"].pop("label")
    case["required"] = ["text", "direction", "target", "expected_decision"]
    prepared["properties"]["tests"] = {
        "type": "object",
        "properties": {key: deepcopy(case) for key in CASE_KEYS},
        "required": list(CASE_KEYS),
        "additionalProperties": False,
    }
    return prepared


def normalize_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    cases = proposal.get("tests")
    if not isinstance(cases, dict) or set(cases) != set(CASE_KEYS):
        raise AuthoringError("invalid_generated_tests")
    if any(
        not isinstance(case, dict) or "label" in case for case in cases.values()
    ):
        raise AuthoringError("invalid_generated_tests")
    normalized = deepcopy(proposal)
    normalized["tests"] = [
        {"label": key, **deepcopy(cases[key])} for key in CASE_KEYS
    ]
    return normalized
