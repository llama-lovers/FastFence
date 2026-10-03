from __future__ import annotations

import json
from typing import Any, Literal

from fastfence.modules.control.contracts.ports import SecretsPort, ToolsPort
from fastfence.modules.control.domain.controls import (
    privacy_filter,
    signature_findings,
)
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.limits import effective_limits
from fastfence.modules.control.domain.models import (
    InvocationState,
    Limits,
    ModelCall,
    ModelPolicy,
    PreparedInvocation,
    Snapshot,
    ToolCall,
    ToolPolicy,
)
from fastfence.modules.control.domain.text_rules import (
    Target,
    text_rule_findings,
)

MODEL_PROMPT_TEMPLATE_ALLOWANCE = 1024


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def check_size(
    value: Any,
    maximum: int,
    direction: Literal["input", "output"],
    findings: list[str] | None = None,
) -> None:
    if len(encode(value).encode()) > maximum:
        raise RejectedError(f"{direction}_too_large", findings)


def inspect_payload(
    value: Any,
    snapshot: Snapshot,
    direction: Literal["input", "output"],
    secrets: SecretsPort | None = None,
    *,
    target: Target = "tool",
) -> tuple[Any, list[str]]:
    policy = snapshot.policy
    maximum = (
        policy.max_input_bytes
        if direction == "input"
        else policy.max_output_bytes
    )
    check_size(value, maximum, direction)
    rule_findings = text_rule_findings(
        policy.text_rules, value, direction, target
    )
    if rule_findings:
        raise RejectedError(f"{direction}_text_rule", rule_findings)
    if policy.signatures_enabled:
        attacks = signature_findings(value, snapshot.feed)
        if attacks:
            reason = (
                "attack_signature"
                if direction == "input"
                else "output_attack_signature"
            )
            raise RejectedError(reason, attacks)
    if not policy.privacy.enabled:
        return value, []
    safe, findings = privacy_filter(value)
    if secrets is not None:
        try:
            safe, detected = secrets.redact(safe)
        except Exception:
            raise RejectedError(
                f"{direction}_secret_detector_unavailable"
            ) from None
        findings = sorted(set(findings).union(detected))
    if any(
        policy.privacy.action_for(finding, direction) == "block"
        for finding in findings
    ):
        raise RejectedError(f"{direction}_sensitive_data", findings)
    check_size(safe, maximum, direction, findings)
    return safe, findings


class InputInspector:
    def __init__(
        self, tools: ToolsPort, secrets: SecretsPort | None = None
    ) -> None:
        self.tools, self.secrets = tools, secrets

    def _authorize(self, state: InvocationState) -> ToolPolicy | ModelPolicy:
        identity, call, policy = (
            state.identity,
            state.call,
            state.snapshot.policy,
        )
        if identity.admin:
            raise RejectedError("admin_credential_cannot_invoke")
        rule = (
            policy.tools.get(call.tool)
            if isinstance(call, ToolCall)
            else policy.models.get(call.model)
        )
        if rule is None:
            state.target = (
                "unknown_tool"
                if isinstance(call, ToolCall)
                else "unknown_model"
            )
            raise RejectedError("target_not_allowlisted")
        if isinstance(call, ToolCall) and not self.tools.supports(call.tool):
            raise RejectedError("tool_not_implemented")
        if not set(identity.roles).intersection(rule.roles):
            raise RejectedError("role_not_allowed")
        return rule

    def prepare(self, state: InvocationState) -> PreparedInvocation:
        rule = self._authorize(state)
        limits = effective_limits(state.identity, state.snapshot.policy)
        if limits is None:
            raise RejectedError("role_budget_missing")
        call = state.call
        original = (
            call.arguments
            if isinstance(call, ToolCall)
            else self._model_payload(call)
        )
        payload, findings = inspect_payload(
            original,
            state.snapshot,
            "input",
            self.secrets,
            target="tool" if isinstance(call, ToolCall) else "model",
        )
        state.findings.update(findings)
        if isinstance(call, ToolCall):
            payload = self.tools.validate(call.tool, payload, state.identity)
        return self._allocation(state, rule, limits, payload)

    @staticmethod
    def _model_payload(call: ModelCall) -> dict[str, Any]:
        payload: dict[str, Any] = (
            {"prompt": call.prompt}
            if call.messages is None
            else {
                "messages": [message.model_dump() for message in call.messages]
            }
        )
        if call.stop is not None:
            payload["stop"] = call.stop
        return payload

    @staticmethod
    def _allocation(
        state: InvocationState,
        rule: ToolPolicy | ModelPolicy,
        limits: Limits,
        payload: dict[str, Any],
    ) -> PreparedInvocation:
        policy, call = state.snapshot.policy, state.call
        input_units = len(encode(payload).encode())
        maximum = (
            min(call.max_output_tokens, rule.max_output_tokens)
            if isinstance(call, ModelCall) and isinstance(rule, ModelPolicy)
            else 0
        )
        base = input_units + (
            maximum + MODEL_PROMPT_TEMPLATE_ALLOWANCE
            if isinstance(call, ModelCall)
            else policy.max_output_bytes
        )
        enabled = policy.semantic.provider != "disabled"
        semantic_reserve = input_units + 2048 if enabled else 0
        if enabled and policy.semantic.scan_output:
            semantic_reserve += policy.max_output_bytes + 2048
        scans = int(enabled) * (2 if policy.semantic.scan_output else 1)
        return PreparedInvocation(
            rule=rule,
            limits=limits,
            payload=payload,
            input_units=input_units,
            max_output_tokens=maximum,
            base_reserve=base,
            reserved_tokens=base + semantic_reserve,
            allocated_ms=rule.timeout_ms + policy.semantic.timeout_ms * scans,
        )
