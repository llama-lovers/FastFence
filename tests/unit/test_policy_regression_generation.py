"""The supported provider envelope assigns labels without repairing semantics."""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from fastfence.modules.control.domain.policy_authoring import DraftEnvelope


@pytest.fixture
def adapter(monkeypatch):
    directory = Path("integrations/laya").resolve()
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "policy_generation_fixture", directory / "policy_generation.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def generated_cases():
    return {
        f"case-{i}": {
            "text": "Cat",
            "target": "model",
            "direction": "input",
            "expected_decision": "no_local_match",
        }
        for i in range(1, 5)
    }


def test_generation_schema_keeps_operations_and_requires_four_explicit_scopes(
    adapter,
):
    original = DraftEnvelope.model_json_schema()
    before = copy.deepcopy(original)
    generated = adapter.generation_schema(original)
    assert original == before
    assert (
        generated["properties"]["operations"]
        == original["properties"]["operations"]
    )
    tests = generated["properties"]["tests"]
    assert tests["type"] == "object" and tests["additionalProperties"] is False
    assert tests["required"] == [f"case-{i}" for i in range(1, 5)]
    for case in tests["properties"].values():
        assert "label" not in case["properties"]
        assert set(case["required"]) == {
            "text",
            "target",
            "direction",
            "expected_decision",
        }


def test_serialization_adapter_never_changes_wrong_expected_or_model_operations(
    adapter,
):
    proposal = {
        "supported": True,
        "operations": [
            {
                "type": "upsert_text_rule",
                "rule": {"id": "fixture", "operator": "contains", "value": "a"},
            }
        ],
        "tests": generated_cases(),
    }
    original = copy.deepcopy(proposal)
    normalized = adapter.normalize_proposal(proposal)
    assert proposal == original
    assert normalized["operations"] == proposal["operations"]
    assert [case["label"] for case in normalized["tests"]] == list(
        adapter.CASE_KEYS
    )
    assert all(
        case["expected_decision"] == "no_local_match"
        for case in normalized["tests"]
    )
    assert len(DraftEnvelope.model_validate(normalized).tests) == 4


@pytest.mark.parametrize(
    "variant", ["missing", "unknown", "extra-label", "wrong-shape"]
)
def test_serialization_adapter_rejects_ambiguous_or_malformed_case_objects(
    adapter, variant
):
    cases = generated_cases()
    if variant == "missing":
        cases.pop("case-1")
    elif variant == "unknown":
        cases["case-5"] = cases.pop("case-1")
    elif variant == "extra-label":
        cases["case-1"]["label"] = "do-not-overwrite"
    else:
        cases["case-1"] = "not-a-case"
    with pytest.raises(adapter.AuthoringError, match="invalid_generated_tests"):
        adapter.normalize_proposal({"tests": cases})
