"""Offline credential-format detectors, with no verification or global settings."""

import re
from collections.abc import Callable, Iterable
from importlib.metadata import version
from itertools import islice
from pathlib import Path
from typing import Any

from detect_secrets.plugins.artifactory import ArtifactoryDetector
from detect_secrets.plugins.aws import AWSKeyDetector
from detect_secrets.plugins.azure_storage_key import AzureStorageKeyDetector
from detect_secrets.plugins.base import BasePlugin, RegexBasedDetector
from detect_secrets.plugins.basic_auth import BasicAuthDetector
from detect_secrets.plugins.discord import DiscordBotTokenDetector
from detect_secrets.plugins.github_token import GitHubTokenDetector
from detect_secrets.plugins.gitlab_token import GitLabTokenDetector
from detect_secrets.plugins.jwt import JwtTokenDetector
from detect_secrets.plugins.keyword import DENYLIST_REGEX, KeywordDetector
from detect_secrets.plugins.mailchimp import MailchimpDetector
from detect_secrets.plugins.openai import OpenAIDetector
from detect_secrets.plugins.private_key import PrivateKeyDetector
from detect_secrets.plugins.pypi_token import PypiTokenDetector
from detect_secrets.plugins.sendgrid import SendGridDetector
from detect_secrets.plugins.slack import SlackDetector
from detect_secrets.plugins.square_oauth import SquareOAuthDetector
from detect_secrets.plugins.stripe import StripeDetector
from detect_secrets.plugins.telegram_token import TelegramBotTokenDetector
from detect_secrets.plugins.twilio import TwilioKeyDetector
from pydantic import ConfigDict

from fastfence.modules.control.domain.frozen import FrozenControlModel
from fastfence.modules.control.persistence.secret_plugins import custom_plugins

MARKER = "[REDACTED:detect_secrets]"
LINE_WRAP = re.compile(r"[ \t]*\r?\n[ \t]*")


class _Detector(FrozenControlModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True, frozen=True, extra="forbid"
    )

    name: str
    analyze: Callable[[str], Iterable[str]]
    patterns: tuple[re.Pattern[str], ...]
    whole_value: bool = False
    necessary_pattern: re.Pattern[str] | None = None


def _configure(plugin: BasePlugin) -> _Detector:
    # The pinned default detector's five patterns all require a quote and a
    # denylisted keyword. Unknown versions/configurations retain the full scan.
    keyword_default = (
        type(plugin) is KeywordDetector
        and plugin.keyword_exclude is None
        and version("detect-secrets") == "1.5.0"
    )
    return _Detector(
        name="detect_secrets_" + type(plugin).__name__,
        analyze=plugin.analyze_string,
        patterns=tuple(plugin.denylist)
        if isinstance(plugin, RegexBasedDetector)
        else (),
        whole_value=isinstance(plugin, PrivateKeyDetector),
        necessary_pattern=re.compile(DENYLIST_REGEX, re.IGNORECASE)
        if keyword_default
        else None,
    )


def _views(text: str) -> Iterable[tuple[str, list[int] | None]]:
    yield text, None
    if "\n" not in text or len(text) > 4096 or text.count("\n") > 8:
        return
    removed: set[int] = set()
    for match in LINE_WRAP.finditer(text):
        removed.update(range(*match.span()))
    positions = [index for index in range(len(text)) if index not in removed]
    yield "".join(text[index] for index in positions), positions


def _candidates(detector: _Detector, text: str) -> set[str]:
    raw = list(islice(detector.analyze(text), 4097))
    if len(raw) > 4096 or any(
        not isinstance(candidate, str) or not candidate or candidate not in text
        for candidate in raw
    ):
        raise ValueError("Secret detector returned invalid results")
    return set(raw)


def _regex_spans(
    detector: _Detector, text: str, candidates: set[str]
) -> list[tuple[int, int]]:
    spans = []
    covered = set()
    for pattern in detector.patterns:
        for match in pattern.finditer(text):
            matching = {
                candidate
                for candidate in candidates
                if candidate in match.group()
            }
            if matching and match.start() < match.end():
                covered.update(matching)
                spans.append(match.span())
    if covered != candidates:
        raise ValueError("Secret detector matches cannot be safely redacted")
    return spans


def _spans(detector: _Detector, text: str) -> Iterable[tuple[int, int]]:
    if detector.necessary_pattern is not None and (
        not any(quote in text for quote in "'\"`")
        or detector.necessary_pattern.search(text) is None
    ):
        return
    candidates = _candidates(detector, text)
    if not candidates:
        return
    if detector.patterns:
        # Some plugins yield capture groups (e.g. GitHub's prefix). Redact the
        # complete matching credential, rather than trusting that yielded substring.
        yield from _regex_spans(detector, text, candidates)
        return
    for candidate in candidates:
        if not candidate:
            continue
        start = 0
        while (position := text.find(candidate, start)) != -1:
            yield position, position + len(candidate)
            start = position + len(candidate)


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(end, merged[-1][1])
        else:
            merged.append((start, end))
    chunks: list[str] = []
    cursor = 0
    for start, end in merged:
        chunks.extend((text[cursor:start], MARKER))
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks)


class OfflineSecrets:
    """Read-only detector configuration; each invocation has private scratch data."""

    def __init__(
        self, plugin_files: tuple[Path, ...] = (), max_file_bytes: int = 65_536
    ) -> None:
        plugins: tuple[BasePlugin, ...] = (
            ArtifactoryDetector(),
            AWSKeyDetector(),
            AzureStorageKeyDetector(),
            BasicAuthDetector(),
            DiscordBotTokenDetector(),
            GitHubTokenDetector(),
            GitLabTokenDetector(),
            JwtTokenDetector(),
            KeywordDetector(),
            MailchimpDetector(),
            OpenAIDetector(),
            PrivateKeyDetector(),
            PypiTokenDetector(),
            SendGridDetector(),
            SlackDetector(),
            SquareOAuthDetector(),
            StripeDetector(),
            TelegramBotTokenDetector(),
            TwilioKeyDetector(),
        )
        plugins += custom_plugins(
            plugin_files,
            max_file_bytes,
            {type(plugin).__name__ for plugin in plugins},
        )
        self._detectors = tuple(_configure(plugin) for plugin in plugins)

    def redact(self, value: Any) -> tuple[Any, list[str]]:
        findings: set[str] = set()
        return self._redact(value, findings), sorted(findings)

    def _redact(self, value: Any, findings: set[str]) -> Any:
        if isinstance(value, str):
            return self._text(value, findings)
        if isinstance(value, dict):
            return {
                self._text(str(key), findings): self._redact(item, findings)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item, findings) for item in value]
        return value

    def _text(self, text: str, findings: set[str]) -> str:
        spans: list[tuple[int, int]] = []
        whole_value = False
        for view, positions in _views(text):
            for detector in self._detectors:
                for start, end in _spans(detector, view):
                    findings.add(detector.name)
                    whole_value |= detector.whole_value
                    span = (
                        (start, end)
                        if positions is None
                        else (positions[start], positions[end - 1] + 1)
                    )
                    spans.append(span)
        return MARKER if whole_value else _mask(text, spans)
