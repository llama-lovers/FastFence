"""Prepared linear-time matching and value-only payload traversal."""

from collections.abc import Callable, Iterator
from typing import Any

from pydantic import ConfigDict

from fastfence.modules.anonymization.domain.tokens import token_spans
from fastfence.shared.anonymization import AnonymizationError, AnonymizationRule
from fastfence.shared.models import StrictModel

MAX_CANDIDATES = 4096


class Span(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: int
    end: int
    rule_index: int


def string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from string_values(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from string_values(item)


def map_values(value: Any, rewrite: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return rewrite(value)
    if isinstance(value, dict):
        return {key: map_values(item, rewrite) for key, item in value.items()}
    if isinstance(value, list):
        return [map_values(item, rewrite) for item in value]
    if isinstance(value, tuple):
        return tuple(map_values(item, rewrite) for item in value)
    return value


def _unprotected_ranges(
    text: str, protected: set[str]
) -> list[tuple[int, int]]:
    protected_spans = [
        (match.start, match.end)
        for match in token_spans(text)
        if match.token in protected
    ]
    ranges, position = [], 0
    for left, right in protected_spans:
        if position < left:
            ranges.append((position, left))
        position = right
    if position < len(text):
        ranges.append((position, len(text)))
    return ranges


def spans(
    text: str, rules: tuple[AnonymizationRule, ...], protected: set[str]
) -> list[Span]:
    ranges = _unprotected_ranges(text, protected)
    candidates: list[Span] = []
    for index, rule in enumerate(rules):
        for match in (
            match
            for left, right in ranges
            for match in rule.compiled.finditer(text, left, right)
        ):
            start, end = match.start(), match.end()
            if start == end:
                raise AnonymizationError("anonymization_empty_match")
            if len(candidates) >= MAX_CANDIDATES:
                raise AnonymizationError("anonymization_capacity")
            candidates.append(Span(start=start, end=end, rule_index=index))
    candidates.sort(key=lambda span: (span.start, -span.end, span.rule_index))
    chosen: list[Span] = []
    previous_end = 0
    for candidate in candidates:
        if candidate.start >= previous_end:
            chosen.append(candidate)
            previous_end = candidate.end
    return chosen
