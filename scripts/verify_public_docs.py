"""Verify publicly served release/dev documentation before announcing success."""

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
SHA = re.compile(r"[0-9a-f]{40}")
MAX_BYTES = 2 * 1024 * 1024


class NotReadyError(Exception):
    """A static diagnostic describing a public response that is not ready."""


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise NotReadyError("unexpected_public_redirect")


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.language = None
        self.canonical = None
        self.links = set()
        self.text = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "html":
            self.language = values.get("lang")
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href")
        if tag == "a" and values.get("href"):
            self.links.add(values["href"])

    def handle_data(self, data):
        self.text.append(data)


def read_public(url, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise NotReadyError("verification_deadline")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    client = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirects()
    )
    request_deadline = min(deadline, time.monotonic() + 10)
    try:
        with client.open(request, timeout=min(10, remaining)) as response:
            if response.status != 200:
                raise NotReadyError("public_response_not_200")
            content = bytearray()
            while True:
                if time.monotonic() >= request_deadline:
                    raise NotReadyError("public_request_deadline")
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(content)))
                if not chunk:
                    return content.decode("utf-8")
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise NotReadyError("public_response_too_large")
    except urllib.error.HTTPError as error:
        raise NotReadyError(f"public_http_{error.code}") from None
    except (OSError, UnicodeError):
        raise NotReadyError("public_request_failed") from None


def inventory(content):
    try:
        entries = json.loads(content)
        if not isinstance(entries, list) or not entries or len(entries) > 1000:
            raise ValueError
        versions = {}
        for entry in entries:
            name = entry["version"]
            aliases = entry["aliases"]
            if (
                not isinstance(name, str)
                or name in versions
                or not isinstance(aliases, list)
                or any(not isinstance(alias, str) for alias in aliases)
                or len(set(aliases)) != len(aliases)
                or not isinstance(entry.get("properties", {}), dict)
            ):
                raise ValueError
            versions[name] = entry
        stable = [name for name in versions if VERSION.fullmatch(name)]
        latest = max(stable, key=lambda name: tuple(map(int, name.split("."))))
        owners = [
            name
            for name, entry in versions.items()
            if "latest" in entry["aliases"]
        ]
        if owners != [latest]:
            raise NotReadyError("latest_alias_is_not_greatest_stable")
        return versions, latest
    except (ValueError, KeyError, TypeError, RecursionError):
        raise NotReadyError("invalid_public_version_inventory") from None


def check_page(
    content, base, channel, language, *, canonical_channel, sha=None
):
    page = Page()
    page.feed(content)
    suffix = "pl/" if language == "pl" else ""
    expected = f"{base}/{canonical_channel}/{suffix}"
    if page.language != language:
        raise NotReadyError("incorrect_public_page_language")
    if page.canonical != expected:
        raise NotReadyError("stale_public_page_canonical")
    if sha is not None:
        source = f"https://github.com/llama-lovers/FastFence/commit/{sha}"
        warning = "niewydana" if language == "pl" else "unreleased"
        if source not in page.links or warning not in " ".join(page.text):
            raise NotReadyError("stale_development_page")
    return f"{base}/{channel}/{suffix}"


def check_once(base, deadline, *, version=None, development_sha=None):
    versions, latest = inventory(read_public(base + "/versions.json", deadline))
    channel = version or "dev"
    expected = (
        {"git_tag": "v" + version} if version else {"git_sha": development_sha}
    )
    properties = versions.get(channel, {}).get("properties", {})
    if any(properties.get(key) != value for key, value in expected.items()):
        raise NotReadyError("requested_documentation_revision_not_public")
    pages = []
    for target, canonical, sha in (
        (channel, channel, development_sha),
        ("latest", latest, None),
    ):
        # The historical 1.0.0 release predates Polish documentation.
        languages = ("en",) if canonical == "1.0.0" else ("en", "pl")
        for language in languages:
            path = f"/{target}/" + ("pl/" if language == "pl" else "")
            pages.append(
                check_page(
                    read_public(base + path, deadline),
                    base,
                    target,
                    language,
                    canonical_channel=canonical,
                    sha=sha,
                )
            )
    return {
        "status": "passed",
        "channel": channel,
        "revision": version or development_sha,
        "latest_stable": latest,
        "public_pages": pages,
    }


def verify(
    *,
    version=None,
    development_sha=None,
    base_url="https://fastfence.dev",
    timeout=600,
    interval=10,
    output=None,
):
    if (version is None) == (development_sha is None):
        raise ValueError(
            "Choose exactly one release version or development SHA"
        )
    if version is not None and not VERSION.fullmatch(version):
        raise ValueError("Use an exact stable release version without v")
    if development_sha is not None and not SHA.fullmatch(development_sha):
        raise ValueError("Use an exact development commit SHA")
    parsed = urllib.parse.urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Use a public HTTPS base URL without credentials or query"
        )
    if not 0 < timeout <= 600 or not 0 < interval <= 15:
        raise ValueError(
            "Verification timeout must be at most 600s and retry delay at most 15s"
        )
    base = base_url.rstrip("/")
    deadline = time.monotonic() + timeout
    reason = "verification_deadline"
    while time.monotonic() < deadline:
        try:
            result = check_once(
                base, deadline, version=version, development_sha=development_sha
            )
            content = json.dumps(result, indent=2) + "\n"
            if output is not None:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(content)
            print(content)
            return result
        except NotReadyError as error:
            reason = str(error)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            print(
                f"Public documentation pending: {reason}; retrying.", flush=True
            )
            time.sleep(min(interval, remaining))
    raise RuntimeError(f"Public documentation verification timed out: {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    channel = parser.add_mutually_exclusive_group(required=True)
    channel.add_argument("--version")
    channel.add_argument("--development-sha")
    parser.add_argument("--base-url", default="https://fastfence.dev")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify(
        version=args.version,
        development_sha=args.development_sha,
        base_url=args.base_url,
        timeout=args.timeout,
        output=args.output,
    )
