from __future__ import annotations

import re
import unicodedata
from typing import Any

from fastfence.core.schema import SignatureFeed

# These are intentionally documented heuristics, not a complete DLP system.
PATTERNS = {
    "secret_api_key": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16})\b"),
    "secret_assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*[\"']?[^\s\"',;]{6,}"
    ),
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "pii_email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "pii_polish_id": re.compile(r"\b\d{11}\b"),
}


def strings(value: Any):
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
    text = normalize("\n".join(strings(value)))
    return [s.id for s in feed.signatures if normalize(s.pattern) in text]


def privacy_filter(value: Any) -> tuple[Any, list[str]]:
    found: set[str] = set()

    def redact(item):
        if isinstance(item, str):
            result = unicodedata.normalize("NFKC", item)
            for name, pattern in PATTERNS.items():
                if pattern.search(result):
                    found.add(name)
                    result = pattern.sub(f"[REDACTED:{name}]", result)
            return result
        if isinstance(item, dict):
            result = {}
            for key, value in item.items():
                safe_key = redact(str(key))
                compact = re.sub(r"[^a-z0-9]", "", normalize(str(key)))
                if (
                    compact
                    in {
                        "password",
                        "apikey",
                        "secret",
                        "accesstoken",
                        "privatekey",
                        "authorization",
                        "credential",
                        "credentials",
                    }
                    and value
                ):
                    found.add("secret_field")
                    result[safe_key] = "[REDACTED:secret_field]"
                else:
                    result[safe_key] = redact(value)
            return result
        if isinstance(item, list):
            return [redact(v) for v in item]
        if isinstance(item, int) and not isinstance(item, bool) and len(str(abs(item))) == 11:
            found.add("pii_polish_id")
            return "[REDACTED:pii_polish_id]"
        return item

    sanitized = redact(value)
    return sanitized, sorted(found)
