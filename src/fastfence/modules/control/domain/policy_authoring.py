"""Bounded policy operations; inference output never bypasses policy validation."""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Any, Literal, Self

from pydantic import (
    Field,
    StrictBool,
    field_serializer,
    field_validator,
    model_validator,
)

from fastfence.modules.control.domain.frozen import FrozenControlModel, Roles
from fastfence.modules.control.domain.models import Policy
from fastfence.modules.control.domain.privacy import (
    PrivacyAction,
    PrivacyDetector,
)
from fastfence.modules.control.domain.text_rules import TextRule

type Scope = Literal["input", "output", "both"]


class UpsertTextRule(FrozenControlModel):
    type: Literal["upsert_text_rule"]
    rule: TextRule


class SetPrivacy(FrozenControlModel):
    type: Literal["set_privacy"]
    direction: Scope
    action: PrivacyAction


class SetPrivacyDetector(FrozenControlModel):
    type: Literal["set_privacy_detector"]
    detector: PrivacyDetector
    direction: Scope
    action: PrivacyAction


class RestrictToolRoles(FrozenControlModel):
    type: Literal["restrict_tool_roles"]
    tool: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,64}$")
    roles: Roles = Field(min_length=1, max_length=32)


type PolicyOperation = Annotated[
    UpsertTextRule | SetPrivacy | SetPrivacyDetector | RestrictToolRoles,
    Field(discriminator="type"),
]


class DraftEnvelope(FrozenControlModel):
    supported: StrictBool
    operations: tuple[PolicyOperation, ...] = Field(max_length=8)

    @model_validator(mode="after")
    def valid_support(self) -> Self:
        if self.supported != bool(self.operations):
            raise ValueError("Supported proposals need operations")
        return self


class PolicyChange(FrozenControlModel):
    path: str
    before: Any
    after: Any

    @field_validator("before", "after")
    @classmethod
    def freeze_values(cls, value: Any) -> Any:
        return freeze_json(value)

    @field_serializer("before", "after")
    def serialize_values(self, value: Any) -> Any:
        return thaw_json(value)


def freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(freeze_json(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


class PreparedPolicy(FrozenControlModel):
    candidate: Policy
    operations: tuple[PolicyOperation, ...]
    changes: tuple[PolicyChange, ...]
    warnings: tuple[str, ...]


def _directions(scope: Scope) -> tuple[str, ...]:
    return ("input", "output") if scope == "both" else (scope,)


def _set_privacy(data: dict[str, Any], operation: SetPrivacy) -> None:
    privacy = data["privacy"]
    privacy["enabled"] = True
    for direction in _directions(operation.direction):
        privacy[direction] = operation.action
        for actions in privacy["detector_actions"].values():
            actions[direction] = None


def _set_detector(data: dict[str, Any], operation: SetPrivacyDetector) -> None:
    privacy = data["privacy"]
    privacy["enabled"] = True
    actions = privacy["detector_actions"].setdefault(
        operation.detector, {"input": None, "output": None}
    )
    for direction in _directions(operation.direction):
        actions[direction] = operation.action


def _restrict_roles(data: dict[str, Any], operation: RestrictToolRoles) -> None:
    tool = data["tools"].get(operation.tool)
    if tool is None or not set(operation.roles).issubset(tool["roles"]):
        raise ValueError("Unknown tool or role widening is unsupported")
    if len(set(operation.roles)) != len(operation.roles):
        raise ValueError("Tool roles must be unique")
    tool["roles"] = list(operation.roles)


def _upsert_rule(data: dict[str, Any], operation: UpsertTextRule) -> None:
    rules = data["text_rules"]
    prepared = operation.rule.model_dump(mode="json")
    for index, existing in enumerate(rules):
        if existing["id"] == operation.rule.id:
            rules[index] = prepared
            return
    rules.append(prepared)


def _changes(
    before: dict[str, Any], after: dict[str, Any], prefix: str = ""
) -> list[PolicyChange]:
    result: list[PolicyChange] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new or key == "version":
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(old, dict) and isinstance(new, dict):
            result.extend(_changes(old, new, path))
        else:
            result.append(PolicyChange(path=path, before=old, after=new))
    return result


def prepare_policy(policy: Policy, envelope: DraftEnvelope) -> PreparedPolicy:
    if not envelope.supported:
        raise ValueError("Unsupported instruction")
    data = policy.editable()
    for operation in envelope.operations:
        if isinstance(operation, UpsertTextRule):
            _upsert_rule(data, operation)
        elif isinstance(operation, SetPrivacy):
            _set_privacy(data, operation)
        elif isinstance(operation, SetPrivacyDetector):
            _set_detector(data, operation)
        else:
            _restrict_roles(data, operation)
    data["version"] = policy.version + 1
    candidate = Policy.model_validate(data)
    changes = tuple(_changes(policy.editable(), candidate.editable()))
    if not changes:
        raise ValueError("Proposal does not change the policy")
    warnings = (
        ("privacy_was_disabled_enabling_existing_detectors",)
        if not policy.privacy.enabled and candidate.privacy.enabled
        else ()
    )
    return PreparedPolicy(
        candidate=candidate,
        operations=envelope.operations,
        changes=changes,
        warnings=warnings,
    )


def authoring_catalog(policy: Policy) -> dict[str, Any]:
    return {
        "privacy_detectors": {
            "pii_email": "Email addresses only",
            "pii_polish_id": "Eleven-digit Polish identifier heuristic only",
        },
        "tools": {
            name: {"currently_allowed_roles": list(tool.roles)}
            for name, tool in policy.tools.items()
        },
        "privacy": policy.privacy.model_dump(mode="json"),
        "existing_text_rule_ids": [rule.id for rule in policy.text_rules],
    }
