"""Bounded textual signature views, never executable payload decoding."""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from functools import lru_cache
from typing import Any
from urllib.parse import unquote

from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.domain.models import Signature, SignatureFeed

MAX_TEXT = 131_072
MAX_NODES = 4096
MAX_VIEWS = 4096
MAX_DECODED = 65_536
MAX_DECODE_CACHE = 256
ZERO_WIDTH = "\u200b\u200c\u200d\ufeff\u2060"
BASE64 = re.compile(
    r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{8,4096}={0,2}(?![A-Za-z0-9+/=_-])"
)


def reject_limit() -> None:
    raise RejectedError("signature_inspection_limit")


def normalize(text: str) -> str:
    return (
        unicodedata.normalize("NFKC", text)
        .casefold()
        .translate(dict.fromkeys(map(ord, ZERO_WIDTH)))
    )


def reconstruct(items: list[Any] | tuple[Any, ...]) -> list[str]:
    """Only join adjacent string siblings, never unrelated mapping fields."""
    result: list[str] = []
    fragments: list[str] = []
    for child in [*items, None]:
        if isinstance(child, str):
            fragments.append(child)
            if len(fragments) > 16 or sum(map(len, fragments)) > 8192:
                reject_limit()
        else:
            if len(fragments) > 1:
                result.append("".join(fragments))
            fragments = []
    return result


def scalar_texts(value: Any) -> list[str]:
    stack = [(value, 0)]
    result: list[str] = []
    nodes = characters = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > 32:
            reject_limit()
        if isinstance(item, str):
            characters += len(item)
            result.append(item)
        elif isinstance(item, dict):
            if len(item) > MAX_NODES:
                reject_limit()
            stack.extend(
                (child, depth + 1) for child in reversed(list(item.values()))
            )
            stack.extend((str(key), depth + 1) for key in item)
        elif isinstance(item, list | tuple):
            if len(item) > MAX_NODES:
                reject_limit()
            stack.extend((child, depth + 1) for child in reversed(item))
            joined = reconstruct(item)
            characters += sum(map(len, joined))
            result.extend(joined)
        if characters > MAX_TEXT or len(result) > MAX_VIEWS:
            reject_limit()
    return result


def decoded_base64(encoded: str) -> tuple[str, int] | None:
    try:
        decoded = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4),
            altchars=b"-_",
            validate=True,
        ).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    if not decoded or not all(
        char.isprintable() or char in "\n\r\t" for char in decoded
    ):
        return None
    return normalize(decoded), len(decoded)


def inspection_views(value: Any) -> list[str]:
    source = scalar_texts(value)
    views: list[str] = []
    decoded_size = candidates = 0
    # Private scratch data for this inspection only, including failed decodes.
    decode_cache: dict[str, tuple[str, int] | None] = {}
    for text in source:
        normalized = normalize(text)
        views.append(normalized)
        if re.search(r"%[0-9a-fA-F]{2}", text):
            try:
                decoded = unquote(text, errors="strict")
            except UnicodeDecodeError:
                raise RejectedError("signature_invalid_encoding") from None
            decoded_size += len(decoded)
            views.append(normalize(decoded))
        for candidate in BASE64.finditer(text):
            encoded = candidate.group()
            if encoded in decode_cache:
                decoded = decode_cache[encoded]
            else:
                decoded = decoded_base64(encoded)
                if len(decode_cache) < MAX_DECODE_CACHE:
                    decode_cache[encoded] = decoded
            if decoded is not None:
                candidates += 1
                if candidates > 1024:
                    reject_limit()
                decoded_size += decoded[1]
                views.append(decoded[0])
        if decoded_size > MAX_DECODED or len(views) > MAX_VIEWS:
            reject_limit()
    return views


def boundary(pattern: str) -> str:
    return (
        (r"(?<!\w)" if pattern[0].isalnum() or pattern[0] == "_" else "")
        + re.escape(pattern)
        + (r"(?!\w)" if pattern[-1].isalnum() or pattern[-1] == "_" else "")
    )


@lru_cache(maxsize=512)
def literal_pattern(pattern: str) -> re.Pattern[str]:
    compact = "".join(char for char in normalize(pattern) if not char.isspace())
    if not compact:
        raise RejectedError("signature_invalid_pattern")
    gap = r"\s{0,8}"
    escaped = gap.join(re.escape(char) for char in compact)
    if compact[0].isalnum() or compact[0] == "_":
        escaped = r"(?<!\w)" + escaped
    if compact[-1].isalnum() or compact[-1] == "_":
        escaped += r"(?!\w)"
    return re.compile(escaped)


@lru_cache(maxsize=512)
def token_patterns(pattern: str) -> tuple[re.Pattern[str], ...]:
    return tuple(
        re.compile(boundary(token)) for token in normalize(pattern).split()
    )


def sequence_matches(text: str, signature: Signature) -> bool:
    previous: list[int] = []
    for index, token in enumerate(token_patterns(signature.pattern)):
        ends: list[int] = []
        cursor = 0
        for match in token.finditer(text):
            if index == 0:
                ends.append(match.end())
            else:
                while (
                    cursor < len(previous)
                    and previous[cursor] < match.start() - signature.max_gap
                ):
                    cursor += 1
                if cursor < len(previous) and previous[cursor] <= match.start():
                    ends.append(match.end())
            if len(ends) > MAX_NODES:
                reject_limit()
        if not ends:
            return False
        previous = ends
    return bool(previous)


def signature_findings(value: Any, feed: SignatureFeed) -> list[str]:
    views = inspection_views(value)
    findings = []
    for signature in feed.signatures:
        literal = literal_pattern(signature.pattern)
        if any(
            literal.search(text)
            or (
                signature.match_mode == "token_sequence"
                and sequence_matches(text, signature)
            )
            for text in views
        ):
            findings.append(signature.id)
    return findings
