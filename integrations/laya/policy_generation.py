"""Lossless generation envelope adapter; rule and expectation values are unchanged."""

from copy import deepcopy
from typing import Any

from authoring_contracts import AuthoringError

CASE_KEYS = tuple(f"case-{index}" for index in range(1, 5))
BOUNDARY_SCOPES = {
    "case-3": {"direction": "output", "target": "model"},
    "case-4": {"direction": "input", "target": "tool"},
}


def generation_schema(schema: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(schema)
    rule = prepared["$defs"]["TextRule"]
    rule["required"] = list(
        dict.fromkeys([*rule["required"], "direction", "target"])
    )
    for field in ("direction", "target"):
        rule["properties"][field].pop("default", None)
    case = deepcopy(prepared["$defs"]["GeneratedPolicyTest"])
    case["properties"].pop("label")
    case["required"] = ["text", "direction", "target", "expected_decision"]
    for field in ("direction", "target"):
        case["properties"][field].pop("default", None)
    cases = {key: deepcopy(case) for key in CASE_KEYS}
    for key, scope in BOUNDARY_SCOPES.items():
        for field, value in scope.items():
            cases[key]["properties"][field]["enum"] = [value]
    prepared["properties"]["tests"] = {
        "type": "object",
        "properties": cases,
        "required": list(CASE_KEYS),
        "additionalProperties": False,
    }
    return prepared


def normalize_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    for operation in proposal.get("operations", []):
        if not isinstance(operation, dict):
            raise AuthoringError("invalid_generated_scope")
        if operation.get("type") == "upsert_text_rule":
            rule = operation.get("rule")
            if (
                not isinstance(rule, dict)
                or not isinstance(rule.get("direction"), str)
                or rule.get("direction") not in {"input", "output", "both"}
                or not isinstance(rule.get("target"), str)
                or rule.get("target") not in {"model", "tool", "all"}
            ):
                raise AuthoringError("invalid_generated_scope")
    cases = proposal.get("tests")
    if not isinstance(cases, dict) or set(cases) != set(CASE_KEYS):
        raise AuthoringError("invalid_generated_tests")
    if any(
        not isinstance(case, dict) or "label" in case for case in cases.values()
    ):
        raise AuthoringError("invalid_generated_tests")
    for key, scope in BOUNDARY_SCOPES.items():
        if any(
            cases[key].get(field) != value for field, value in scope.items()
        ):
            raise AuthoringError("invalid_generated_case_scope")
    normalized = deepcopy(proposal)
    normalized["tests"] = [
        {"label": key, **deepcopy(cases[key])} for key in CASE_KEYS
    ]
    return normalized
