"""Bounded literal text restrictions, prepared when trusted policy is validated."""

import unicodedata
from collections.abc import Iterator
from typing import Any, Literal, Self

from pydantic import Field, PrivateAttr, field_validator, model_validator

from fastfence.modules.control.domain.frozen import FrozenControlModel

type Direction = Literal["input", "output"]
type Target = Literal["model", "tool"]


def normalized(text: str, case_sensitive: bool) -> str:
    value = unicodedata.normalize("NFKC", text)
    return value if case_sensitive else value.casefold()


def word_character(character: str) -> bool:
    return unicodedata.category(character)[0] in {"L", "M"}


class TextRule(FrozenControlModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    operator: Literal["contains", "word_contains", "equals"]
    value: str = Field(min_length=1, max_length=128)
    direction: Literal["input", "output", "both"] = "both"
    target: Literal["model", "tool", "all"] = "model"
    action: Literal["block"] = "block"
    case_sensitive: bool = False
    _normalized_value: str = PrivateAttr(default="")

    @field_validator("value", mode="before")
    @classmethod
    def trim_value(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def prepare_literal(self) -> Self:
        object.__setattr__(
            self,
            "_normalized_value",
            normalized(self.value, self.case_sensitive),
        )
        if self.operator == "word_contains" and (
            not all(word_character(char) for char in self._normalized_value)
            or not any(char.isalpha() for char in self._normalized_value)
        ):
            raise ValueError("word_contains requires one Unicode letter word")
        return self

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_normalized_value":
            raise TypeError("Prepared rule literal is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name == "_normalized_value":
            raise TypeError("Prepared rule literal is immutable")
        super().__delattr__(name)


def _matches(rule: TextRule, text: str) -> bool:
    needle = rule._normalized_value
    if rule.operator == "equals":
        return text == needle
    # word_contains literals consist only of letters/marks and contain a letter.
    # Their occurrence is therefore inside a Unicode word, including a longer word.
    return needle in text


def text_rule_matches(rule: TextRule, text: str) -> bool:
    """Evaluate one validated rule against content, without I/O or execution."""
    return _matches(rule, normalized(text, rule.case_sensitive))


def _string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)


def _model_content(value: Any, direction: Direction) -> Iterator[str]:
    if not isinstance(value, dict):
        return
    if direction == "output":
        text = value.get("text")
        if isinstance(text, str):
            yield text
        return
    prompt = value.get("prompt")
    if isinstance(prompt, str):
        yield prompt
    messages = value.get("messages", [])
    for message in messages if isinstance(messages, list) else []:
        if isinstance(message, dict) and isinstance(
            message.get("content"), str
        ):
            yield message["content"]
    stop = value.get("stop", [])
    for item in stop if isinstance(stop, list) else []:
        if isinstance(item, str):
            yield item


def text_rule_findings(
    rules: tuple[TextRule, ...],
    value: Any,
    direction: Direction,
    target: Target,
) -> list[str]:
    active = tuple(
        rule
        for rule in rules
        if rule.direction in {direction, "both"}
        and rule.target in {target, "all"}
    )
    if not active:
        return []
    texts = (
        _model_content(value, direction)
        if target == "model"
        else _string_values(value)
    )
    findings: set[str] = set()
    for text in texts:
        prepared = {
            sensitive: normalized(text, sensitive)
            for sensitive in {rule.case_sensitive for rule in active}
        }
        for rule in active:
            if rule.id not in findings and _matches(
                rule, prepared[rule.case_sensitive]
            ):
                findings.add(rule.id)
    return sorted(findings)
