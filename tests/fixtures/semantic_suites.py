"""Reviewed synthetic semantic cases; no real model assumptions."""

from fastfence.app.interfaces.http.semantic_review_models import SemanticCase
from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.semantic_rules import SemanticRule


def suite_rule(identifier="topic"):
    return SemanticRule(
        id=identifier,
        instruction="Block restricted topics.",
        direction="input",
        target="model",
    )


def suite_cases():
    return (
        SemanticCase(
            id="deny",
            text="Synthetic restricted topic",
            direction="input",
            target="model",
            expected="blocked",
        ),
        SemanticCase(
            id="permit",
            text="Synthetic ordinary topic",
            direction="input",
            target="model",
            expected="no_semantic_block",
        ),
    )


def suite_policy(base, *rules):
    data = base.model_dump(mode="json")
    data["version"] += 1
    data["semantic"].update(
        provider="laya",
        model="qwen3:4b",
        rules=[rule.model_dump() for rule in rules],
    )
    return Policy.model_validate(data)
