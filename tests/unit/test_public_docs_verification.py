"""Public deployment gates detect stale CDN content despite green Pages status."""

import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from scripts import verify_public_docs as docs

BASE = "https://fastfence.dev"
SHA = "a" * 40


def inventory():
    return [
        {"version": "dev", "aliases": [], "properties": {"git_sha": SHA}},
        {
            "version": "1.0.1",
            "aliases": ["latest"],
            "properties": {"git_tag": "v1.0.1"},
        },
        {
            "version": "1.0.0",
            "aliases": [],
            "properties": {"git_tag": "v1.0.0"},
        },
    ]


def page(channel, language="en", sha=None):
    suffix = "pl/" if language == "pl" else ""
    warning = "niewydana" if language == "pl" else "unreleased"
    source = (
        f'<a href="https://github.com/llama-lovers/FastFence/commit/{sha}">{warning}</a>'
        if sha
        else ""
    )
    return f'<html lang="{language}"><link rel="canonical" href="{BASE}/{channel}/{suffix}">{source}<a hreflang="pl">Polski</a></html>'


def fixture(monkeypatch, entries=None):
    responses = {BASE + "/versions.json": json.dumps(entries or inventory())}
    for channel in ("1.0.0", "1.0.1", "latest", "dev"):
        for language in ("en", "pl"):
            if channel == "1.0.0" and language == "pl":
                continue
            suffix = "pl/" if language == "pl" else ""
            responses[f"{BASE}/{channel}/{suffix}"] = page(
                "1.0.1" if channel == "latest" else channel,
                language,
                SHA if channel == "dev" else None,
            )
    requested = []

    def read(url, deadline):
        requested.append(url)
        return responses[url]

    monkeypatch.setattr(docs, "read_public", read)
    return responses, requested


@pytest.mark.parametrize(
    "kwargs", [{"version": "1.0.1"}, {"development_sha": SHA}]
)
def test_current_channel_and_latest_bilingual_pages_pass(
    monkeypatch, tmp_path, kwargs
):
    _, requested = fixture(monkeypatch)
    output = tmp_path / "evidence.json"
    result = docs.verify(**kwargs, output=output)
    assert json.loads(output.read_text()) == result
    assert result["latest_stable"] == "1.0.1"
    assert len(requested) == 5
    assert BASE + "/latest/pl/" in requested


def test_historical_release_does_not_require_missing_translation(monkeypatch):
    _, requested = fixture(monkeypatch)
    docs.check_once(BASE, 100, version="1.0.0")
    assert BASE + "/1.0.0/pl/" not in requested
    assert BASE + "/latest/pl/" in requested


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda x: x.pop(1), "latest_alias"),
        (
            lambda x: x[0]["properties"].update(git_sha="b" * 40),
            "requested_documentation",
        ),
        (lambda x: x[0]["aliases"].append("latest"), "latest_alias"),
        (
            lambda x: (
                x[1].update(aliases=[]),
                x[2].update(aliases=["latest"]),
            ),
            "latest_alias",
        ),
        (lambda x: x[0].update(aliases=None), "invalid_public"),
        (lambda x: x.append(x[0]), "invalid_public"),
    ],
)
def test_stale_or_invalid_inventory_fails(monkeypatch, mutation, reason):
    entries = inventory()
    mutation(entries)
    fixture(monkeypatch, entries)
    with pytest.raises(docs.NotReadyError, match=reason):
        docs.check_once(BASE, 100, development_sha=SHA)


def test_missing_requested_release_rejected(monkeypatch):
    fixture(monkeypatch)
    with pytest.raises(docs.NotReadyError, match="requested_documentation"):
        docs.check_once(BASE, 100, version="1.0.2")


@pytest.mark.parametrize(
    "url,content,reason",
    [
        ("/latest/", page("1.0.0"), "stale_public_page_canonical"),
        ("/1.0.1/pl/", page("1.0.1", "en"), "incorrect_public_page_language"),
        ("/dev/", page("dev", sha="b" * 40), "stale_development_page"),
        (
            "/dev/pl/",
            page("dev", "pl", SHA).replace("niewydana", "released"),
            "stale_development_page",
        ),
    ],
)
def test_right_inventory_cannot_hide_stale_pages(
    monkeypatch, url, content, reason
):
    responses, _ = fixture(monkeypatch)
    responses[BASE + url] = content
    kwargs = (
        {"development_sha": SHA}
        if url.startswith("/dev")
        else {"version": "1.0.1"}
    )
    with pytest.raises(docs.NotReadyError, match=reason):
        docs.check_once(BASE, 100, **kwargs)


def fake_clock(monkeypatch):
    clock = [0]
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(docs.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(docs.time, "sleep", sleep)
    return waits


def test_retry_then_success_records_only_verified_evidence(
    monkeypatch, tmp_path
):
    waits = fake_clock(monkeypatch)
    calls = []

    def check(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise docs.NotReadyError("stale_public_page_canonical")
        return {"status": "passed"}

    monkeypatch.setattr(docs, "check_once", check)
    assert (
        docs.verify(
            version="1.0.1",
            timeout=40,
            interval=15,
            output=tmp_path / "proof.json",
        )["status"]
        == "passed"
    )
    assert waits == [15, 15]


def test_timeout_is_bounded_and_does_not_write_success(monkeypatch, tmp_path):
    waits = fake_clock(monkeypatch)

    def check(*args, **kwargs):
        raise docs.NotReadyError("requested_documentation_revision_not_public")

    monkeypatch.setattr(docs, "check_once", check)
    output = tmp_path / "proof.json"
    with pytest.raises(RuntimeError, match="timed out"):
        docs.verify(version="1.0.1", timeout=32, interval=15, output=output)
    assert waits == [15, 15, 2]
    assert not output.exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"version": "1.0.1", "development_sha": SHA},
        {"version": "../x"},
        {"development_sha": "main"},
        {"version": "1.0.1", "base_url": "http://fastfence.dev"},
        {
            "version": "1.0.1",
            "base_url": "https://user:secret@fastfence.dev",  # pragma: allowlist secret - synthetic rejected URL
        },
        {"version": "1.0.1", "base_url": "https://fastfence.dev?nocache=1"},
        {"version": "1.0.1", "timeout": 601},
        {"version": "1.0.1", "interval": 16},
    ],
)
def test_invalid_inputs_fail_before_requests(monkeypatch, kwargs):
    monkeypatch.setattr(
        docs, "check_once", lambda *a, **kw: pytest.fail("unexpected request")
    )
    with pytest.raises(ValueError):
        docs.verify(**kwargs)


def test_public_request_has_no_auth_proxy_or_query(monkeypatch):
    response = io.BytesIO(b"public")
    response.status = 200
    captured = {}

    def opener(*handlers):
        assert handlers[0].proxies == {}
        assert isinstance(handlers[1], docs.NoRedirects)

        def open_request(request, timeout):
            captured.update(
                url=request.full_url,
                headers=dict(request.header_items()),
                timeout=timeout,
            )
            return response

        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(docs.urllib.request, "build_opener", opener)
    assert (
        docs.read_public(BASE + "/versions.json", docs.time.monotonic() + 30)
        == "public"
    )
    assert captured == {
        "url": BASE + "/versions.json",
        "headers": {"User-agent": "Mozilla/5.0"},
        "timeout": 10,
    }


def test_redirect_is_not_followed():
    with pytest.raises(docs.NotReadyError, match="unexpected_public_redirect"):
        docs.NoRedirects().redirect_request(
            None, None, 302, None, None, "https://other.test"
        )


@pytest.mark.parametrize(
    "payload,reason",
    [
        (b"x" * (docs.MAX_BYTES + 1), "too_large"),
        (b"\xff", "public_request_failed"),
    ],
)
def test_response_bounds_and_encoding(monkeypatch, payload, reason):
    response = io.BytesIO(payload)
    response.status = 200
    monkeypatch.setattr(
        docs.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=lambda *a, **kw: response),
    )
    with pytest.raises(docs.NotReadyError, match=reason):
        docs.read_public(BASE, docs.time.monotonic() + 30)


def test_http_failure_withholds_body_and_reason(monkeypatch):
    def open_request(*args, **kwargs):
        raise urllib.error.HTTPError(
            BASE, 404, "private provider details", {}, io.BytesIO(b"private")
        )

    monkeypatch.setattr(
        docs.urllib.request,
        "build_opener",
        lambda *a: SimpleNamespace(open=open_request),
    )
    with pytest.raises(docs.NotReadyError, match="^public_http_404$"):
        docs.read_public(BASE, docs.time.monotonic() + 30)
