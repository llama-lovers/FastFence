from __future__ import annotations

import asyncio
import json
import time
import uuid

from pydantic import ValidationError

from fastfence.actions.tools import DemoTools, ResourceDenied
from fastfence.adapters.models import ModelUnavailable, OllamaModels, SemanticScanner
from fastfence.core.controls import privacy_filter, signature_findings
from fastfence.core.policy import PolicyStore
from fastfence.core.schema import Identity, Limits, ModelCall, ToolCall, Verdict
from fastfence.data.ledger import BudgetExceeded, Ledger


class Rejected(Exception):
    def __init__(self, reason: str, findings: list[str] | None = None):
        self.reason, self.findings = reason, findings or []


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Engine:
    def __init__(
        self,
        policies: PolicyStore,
        ledger: Ledger,
        tools: DemoTools,
        scanner: SemanticScanner,
        models: OllamaModels,
    ):
        self.policies, self.ledger, self.tools = policies, ledger, tools
        self.scanner, self.models = scanner, models

    async def invoke(self, identity: Identity, call: ToolCall | ModelCall) -> Verdict:
        start = time.monotonic()
        snapshot = self.policies.snapshot()
        policy, feed = snapshot.policy, snapshot.feed
        request_id = uuid.uuid4().hex
        target = call.tool if isinstance(call, ToolCall) else "llm:" + call.model
        verdict = Verdict(
            request_id=request_id,
            decision="blocked",
            reason="access_denied",
            policy_version=policy.version,
            feed_version=feed.version,
            latency_ms=0,
            semantic_provider=policy.semantic.provider,
        )
        reserved = False
        reserved_tokens = 0
        tokens = 0
        cost = 0
        cancelled = False
        all_findings: set[str] = set()
        semantic_score = None
        try:
            if identity.admin:
                raise Rejected("admin_credential_cannot_invoke")
            rule = (
                policy.tools.get(call.tool)
                if isinstance(call, ToolCall)
                else policy.models.get(call.model)
            )
            if rule is None:
                target = "unknown_tool" if isinstance(call, ToolCall) else "unknown_model"
                raise Rejected("target_not_allowlisted")
            if isinstance(call, ToolCall) and call.tool not in self.tools.schemas:
                raise Rejected("tool_not_implemented")
            if not set(identity.roles).intersection(rule.roles):
                raise Rejected("role_not_allowed")
            budgets = [policy.budgets[r] for r in identity.roles if r in policy.budgets]
            if not budgets:
                raise Rejected("role_budget_missing")
            limits = Limits(
                **{field: min(getattr(b, field) for b in budgets) for field in Limits.model_fields}
            )
            payload = call.arguments if isinstance(call, ToolCall) else {"prompt": call.prompt}
            text = encode(payload)
            if len(text.encode()) > policy.max_input_bytes:
                raise Rejected("input_too_large")
            if policy.signatures_enabled:
                attacks = signature_findings(payload, feed)
                if attacks:
                    raise Rejected("attack_signature", attacks)
            if policy.privacy.enabled:
                safe_payload, findings = privacy_filter(payload)
                if findings and policy.privacy.input == "block":
                    raise Rejected("input_sensitive_data", findings)
                payload = safe_payload
                all_findings.update(findings)
            if isinstance(call, ToolCall):
                payload = self.tools.validate(call.tool, payload, identity)
            text = encode(payload)
            input_units = len(text.encode())
            sem = policy.semantic.provider != "disabled"
            max_output_tokens = (
                min(call.max_output_tokens, rule.max_output_tokens)
                if isinstance(call, ModelCall)
                else 0
            )
            base_reserve = input_units + (
                max_output_tokens if isinstance(call, ModelCall) else policy.max_output_bytes
            )
            semantic_reserve = (input_units + 2048) if sem else 0
            if sem and policy.semantic.scan_output:
                semantic_reserve += policy.max_output_bytes + 2048
            reserved_tokens = base_reserve + semantic_reserve
            allocated_ms = rule.timeout_ms + (
                policy.semantic.timeout_ms * (2 if policy.semantic.scan_output else 1) if sem else 0
            )
            self.ledger.reserve(
                request_id,
                identity.subject,
                limits,
                reserved_tokens,
                rule.cost_microusd,
                allocated_ms,
            )
            reserved = True
            tokens = input_units
            if sem:
                # Charge conservative reservation on failure rather than making failed scans free.
                tokens += input_units + 2048
                assessment = await asyncio.wait_for(
                    self.scanner.assess(text, policy.semantic), policy.semantic.timeout_ms / 1000
                )
                if assessment.tokens > input_units + 2048:
                    raise Rejected("semantic_usage_exceeded")
                tokens -= input_units + 2048 - assessment.tokens
                semantic_score = assessment.score
                if assessment.score >= policy.semantic.threshold:
                    raise Rejected("semantic_input_risk", ["semantic_injection"])
            verdict.upstream_executed = True
            cost = rule.cost_microusd
            if isinstance(call, ToolCall):
                output = await asyncio.wait_for(
                    self.tools.call(call.tool, payload, identity), timeout=rule.timeout_ms / 1000
                )
                output_units = len(encode(output).encode())
            else:
                output, model_units = await asyncio.wait_for(
                    self.models.complete(
                        call.model, payload["prompt"], max_output_tokens, rule.timeout_ms
                    ),
                    timeout=rule.timeout_ms / 1000,
                )
                if model_units > base_reserve:
                    raise Rejected("model_usage_exceeded")
                output_units = model_units - input_units
            if len(encode(output).encode()) > policy.max_output_bytes:
                tokens = reserved_tokens
                raise Rejected("output_too_large")
            tokens += max(0, output_units)
            if policy.signatures_enabled:
                attacks = signature_findings(output, feed)
                if attacks:
                    raise Rejected("output_attack_signature", attacks)
            if policy.privacy.enabled:
                safe_output, findings = privacy_filter(output)
                if findings and policy.privacy.output == "block":
                    raise Rejected("output_sensitive_data", findings)
                output = safe_output
                all_findings.update(findings)
            if sem and policy.semantic.scan_output:
                tokens += policy.max_output_bytes + 2048
                assessment = await asyncio.wait_for(
                    self.scanner.assess(encode(output), policy.semantic),
                    policy.semantic.timeout_ms / 1000,
                )
                if assessment.tokens > policy.max_output_bytes + 2048:
                    raise Rejected("semantic_usage_exceeded")
                tokens -= policy.max_output_bytes + 2048 - assessment.tokens
                semantic_score = max(semantic_score or 0, assessment.score)
                if assessment.score >= policy.semantic.threshold:
                    raise Rejected("semantic_output_risk", ["semantic_injection"])
            verdict.output = output
            verdict.decision = "redacted" if all_findings else "allowed"
            verdict.reason = "privacy_redacted" if all_findings else "controls_passed"
        except Rejected as e:
            verdict.reason = e.reason
            all_findings.update(e.findings)
        except ResourceDenied:
            verdict.reason = "cross_tenant_resource"
        except ValidationError:
            verdict.reason = "invalid_tool_arguments"
        except BudgetExceeded as e:
            verdict.reason = str(e)
        except ModelUnavailable:
            verdict.decision = "error"
            verdict.reason = "model_unavailable_fail_closed"
        except TimeoutError:
            tokens = reserved_tokens
            verdict.decision = "error"
            verdict.reason = "upstream_timeout"
        except asyncio.CancelledError:
            tokens = reserved_tokens
            verdict.decision = "error"
            verdict.reason = "request_cancelled"
            cancelled = True
        except Exception:
            tokens = reserved_tokens
            verdict.decision = "error"
            verdict.reason = "upstream_failure"
        finally:
            verdict.latency_ms = max(1, int((time.monotonic() - start) * 1000))
            verdict.findings = sorted(all_findings)
            verdict.semantic_score = semantic_score
            verdict.tokens = tokens if reserved else 0
            verdict.cost_microusd = cost
            if reserved:
                self.ledger.settle(request_id, tokens, cost, verdict.latency_ms)
            self.ledger.append(identity.subject, identity.tenant, target, verdict)
        if cancelled:
            raise asyncio.CancelledError
        return verdict
