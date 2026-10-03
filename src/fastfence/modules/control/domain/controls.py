from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import Any

from fastfence.modules.control.domain.models import SignatureFeed
from fastfence.modules.control.domain.signature_matching import (
    signature_findings as match_signatures,
)

# These are intentionally documented heuristics, not a complete DLP system.
PATTERNS = {
    "secret_api_key": re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16})\b"
    ),
    "secret_assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*[\"']?[^\s\"',;]{6,}"
    ),
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "pii_email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "pii_polish_id": re.compile(r"\b\d{11}\b"),
}


def strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def signature_findings(value: Any, feed: SignatureFeed) -> list[str]:
    return match_signatures(value, feed)


def privacy_filter(value: Any) -> tuple[Any, list[str]]:
    found: set[str] = set()
    return _redact(value, found), sorted(found)


def _redact_text(item: str, found: set[str]) -> str:
    result = unicodedata.normalize("NFKC", item)
    for name, pattern in PATTERNS.items():
        if pattern.search(result):
            found.add(name)
            result = pattern.sub(f"[REDACTED:{name}]", result)
    return result


def _redact_mapping(item: dict[Any, Any], found: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    sensitive = {
        "password",
        "apikey",
        "secret",
        "accesstoken",
        "privatekey",
        "authorization",
        "credential",
        "credentials",
    }
    for key, value in item.items():
        safe_key = _redact_text(str(key), found)
        compact = re.sub(r"[^a-z0-9]", "", normalize(str(key)))
        if compact in sensitive and value:
            found.add("secret_field")
            result[safe_key] = "[REDACTED:secret_field]"
        else:
            result[safe_key] = _redact(value, found)
    return result


def _redact(item: Any, found: set[str]) -> Any:
    if isinstance(item, str):
        return _redact_text(item, found)
    if isinstance(item, dict):
        return _redact_mapping(item, found)
    if isinstance(item, list):
        return [_redact(value, found) for value in item]
    if (
        isinstance(item, int)
        and not isinstance(item, bool)
        and len(str(abs(item))) == 11
    ):
        found.add("pii_polish_id")
        return "[REDACTED:pii_polish_id]"
    return item
