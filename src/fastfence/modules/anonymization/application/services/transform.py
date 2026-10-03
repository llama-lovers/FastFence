"""Stateless value transformations and authenticated token recovery."""

from typing import Any

from fastfence.modules.anonymization.contracts.ports import TokenPort
from fastfence.modules.anonymization.domain.matching import (
    map_values,
    spans,
    string_values,
)
from fastfence.modules.anonymization.domain.tokens import (
    VerifiedToken,
    parse_token,
    token_spans,
)
from fastfence.shared.anonymization import (
    AnonymizationConfig,
    AnonymizationContext,
    AnonymizationDirection,
    AnonymizationError,
    AnonymizationResult,
    AnonymizationTarget,
)


class AnonymizationService:
    def __init__(
        self, codec: TokenPort, *, max_replacements: int = 256
    ) -> None:
        if not 1 <= max_replacements <= 4096:
            raise ValueError("Invalid anonymization replacement limit")
        self.codec = codec
        self.max_replacements = max_replacements

    def _tokens(
        self,
        value: Any,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: AnonymizationTarget,
    ) -> dict[str, VerifiedToken]:
        available = {
            rule.id: rule
            for rule in config.rules
            if rule.target in {target, "all"}
        }
        verified: dict[str, VerifiedToken] = {}
        count = 0
        for text in string_values(value):
            for span in token_spans(text, max_tokens=self.max_replacements):
                count += 1
                if count > self.max_replacements:
                    raise AnonymizationError("anonymization_capacity")
                if span.token in verified:
                    continue
                parsed = parse_token(span.token)
                rule = available.get(parsed.rule_id)
                if not config.enabled or rule is None:
                    raise AnonymizationError("anonymization_invalid_token")
                token = self.codec.verify(span.token, rule, context)
                if token.mode == "reversible" and config.mode != "reversible":
                    raise AnonymizationError("anonymization_restore_denied")
                verified[span.token] = token
        return verified

    def transform(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        direction: AnonymizationDirection,
        target: AnonymizationTarget,
    ) -> AnonymizationResult:
        protected = self._tokens(value, context, config, target)
        if not config.enabled or not config.rules:
            return AnonymizationResult(value=value)
        rules = tuple(
            rule
            for rule in config.rules
            if rule.direction in {direction, "both"}
            and rule.target in {target, "all"}
        )
        memo: dict[tuple[str, str], str] = {}
        findings: set[str] = set()
        total = 0

        def rewrite(text: str) -> str:
            nonlocal total
            pieces, position = [], 0
            for span in spans(text, rules, set(protected)):
                total += 1
                if total > self.max_replacements:
                    raise AnonymizationError("anonymization_capacity")
                rule = rules[span.rule_index]
                original = text[span.start : span.end]
                key = rule.fingerprint, original
                if key not in memo:
                    memo[key] = self.codec.issue(
                        rule, original, context, config.mode
                    )
                pieces.extend((text[position : span.start], memo[key]))
                position = span.end
                findings.add(rule.id)
            pieces.append(text[position:])
            return "".join(pieces)

        result = map_values(value, rewrite)
        return AnonymizationResult(
            value=result, findings=sorted(findings), changed=bool(findings)
        )

    def _reveal(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: AnonymizationTarget,
        authorized: bool,
    ) -> AnonymizationResult:
        verified = self._tokens(value, context, config, target)
        active = {rule.id: rule for rule in config.rules}
        findings: set[str] = set()
        if authorized and (not config.enabled or config.mode != "reversible"):
            raise AnonymizationError("anonymization_restore_denied")

        def rewrite(text: str) -> str:
            pieces, position = [], 0
            for span in token_spans(text):
                token = verified[span.token]
                if authorized and (
                    token.original is None
                    or not active[token.rule_id].allow_restore
                ):
                    raise AnonymizationError("anonymization_restore_denied")
                replacement = (
                    token.original if token.original is not None else span.token
                )
                pieces.extend((text[position : span.start], replacement))
                position = span.end
                if token.original is not None:
                    findings.add(token.rule_id)
            pieces.append(text[position:])
            return "".join(pieces)

        result = map_values(value, rewrite)
        return AnonymizationResult(
            value=result, findings=sorted(findings), changed=bool(findings)
        )

    def restore(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: AnonymizationTarget = "model",
    ) -> AnonymizationResult:
        return self._reveal(
            value,
            context=context,
            config=config,
            target=target,
            authorized=True,
        )

    def reveal_for_checks(
        self,
        value: Any,
        *,
        context: AnonymizationContext,
        config: AnonymizationConfig,
        target: AnonymizationTarget,
    ) -> AnonymizationResult:
        return self._reveal(
            value,
            context=context,
            config=config,
            target=target,
            authorized=False,
        )
