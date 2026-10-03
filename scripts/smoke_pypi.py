"""Verify exact public PyPI release bytes and test a fresh index installation."""

import argparse
import hashlib
import json
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if __package__:
    from .smoke_wheel import smoke
else:
    from smoke_wheel import smoke

MAX_WHEEL_BYTES = 20 * 1024 * 1024


class AwaitingPublicationError(Exception):
    """The exact release or its wheel has not propagated yet."""


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        raise ValueError(
            "Public package verification does not follow redirects"
        )


def read_public(url, maximum):
    client = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirects()
    )
    with client.open(url, timeout=15) as response:
        content = response.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("Public package response exceeds verification limit")
    return content


def wheel_metadata(version):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Expected an exact three-part release version")
    metadata = json.loads(
        read_public(
            f"https://pypi.org/pypi/fastfence/{version}/json", 2 * 1024 * 1024
        )
    )
    if (
        metadata["info"]["name"] != "fastfence"
        or metadata["info"]["version"] != version
    ):
        raise ValueError(
            "Public metadata does not match requested project/version"
        )
    filename = f"fastfence-{version}-py3-none-any.whl"
    candidates = [
        entry for entry in metadata["urls"] if entry["filename"] == filename
    ]
    if not candidates:
        raise AwaitingPublicationError(
            "The exact release wheel is not visible yet"
        )
    if len(candidates) != 1:
        raise ValueError("Ambiguous release wheel metadata")
    entry = candidates[0]
    url = urllib.parse.urlsplit(entry["url"])
    if (
        entry["packagetype"] != "bdist_wheel"
        or entry["yanked"]
        or url.scheme != "https"
        or url.netloc != "files.pythonhosted.org"
        or url.query
        or url.fragment
        or not url.path.endswith("/" + filename)
        or not re.fullmatch(r"[a-f0-9]{64}", entry["digests"]["sha256"])
        or type(entry["size"]) is not int
        or not 0 < entry["size"] <= MAX_WHEEL_BYTES
    ):
        raise ValueError("Unsafe or invalid public wheel metadata")
    return entry


def download_release(version, directory, *, attempts=12, delay=10):
    for attempt in range(attempts):
        try:
            entry = wheel_metadata(version)
            content = read_public(entry["url"], MAX_WHEEL_BYTES)
            break
        except urllib.error.HTTPError as error:
            if error.code not in {404, 429, 500, 502, 503, 504}:
                raise
        except (AwaitingPublicationError, urllib.error.URLError, TimeoutError):
            pass
        if attempt + 1 == attempts:
            raise RuntimeError(
                "Exact public PyPI release did not become available within retry limit"
            )
        print(
            f"Waiting for public PyPI release {version} ({attempt + 1}/{attempts})"
        )
        time.sleep(delay)
    digest = hashlib.sha256(content).hexdigest()
    if len(content) != entry["size"] or digest != entry["digests"]["sha256"]:
        raise ValueError(
            "Public wheel size or SHA256 does not match PyPI metadata"
        )
    path = directory / entry["filename"]
    path.write_bytes(content)
    return path, digest


def verify(version, *, expected_wheel=None, output=None, attempts=12, delay=10):
    with tempfile.TemporaryDirectory(
        prefix="fastfence-public-pypi-"
    ) as temporary:
        wheel, digest = download_release(
            version, Path(temporary), attempts=attempts, delay=delay
        )
        if expected_wheel is not None:
            if (
                expected_wheel.name != wheel.name
                or hashlib.sha256(expected_wheel.read_bytes()).hexdigest()
                != digest
            ):
                raise ValueError(
                    "Published wheel differs from the verified build artifact"
                )
        smoke(wheel, pypi_version=version)
    result = {
        "version": version,
        "index": "https://pypi.org/simple",
        "sha256": digest,
        "status": "passed",
        "isolated_index_install": True,
        "installed_files_match_public_wheel": True,
        "matches_verified_build": expected_wheel is not None,
        "scope": "Installed-package CLI, initialization, bundled helpers, HTTP assets and fail-closed invocation; no live model/OCR inference.",
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--expected-wheel", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--attempts", type=int, choices=range(1, 21), default=12
    )
    parser.add_argument("--delay", type=int, choices=range(1, 31), default=10)
    args = parser.parse_args()
    verify(
        args.version,
        expected_wheel=args.expected_wheel,
        output=args.output,
        attempts=args.attempts,
        delay=args.delay,
    )
