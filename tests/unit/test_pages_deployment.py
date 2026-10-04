"""Pages publication keeps site identity separate from source and protects tokens."""

import io
import runpy
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = runpy.run_path(str(ROOT / "scripts/deploy_pages.py"))
DEPLOY = SCRIPT["deploy"]
ERROR = SCRIPT["DeploymentError"]
SHA = "a" * 40
ENV = {
    "GITHUB_REPOSITORY": "llama-lovers/FastFence",
    "GITHUB_TOKEN": "test-github-secret",
    "GITHUB_SHA": "b" * 40,
    "ACTIONS_ID_TOKEN_REQUEST_URL": "https://run.actions.githubusercontent.com/idtoken?job=1",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "test-oidc-request-secret",
}
ENDPOINT = (
    "https://api.github.com/repos/llama-lovers/FastFence/pages/deployments"
)


def scripted_request(states, *, created=None):
    calls = []
    values = iter(states)

    def request(url, token, **kwargs):
        calls.append((url, token, kwargs))
        if url == ENV["ACTIONS_ID_TOKEN_REQUEST_URL"]:
            return {"value": "test-issued-oidc-secret"}
        if url == ENDPOINT:
            return {"id": SHA} if created is None else created
        if url.endswith("/cancel"):
            return {}
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return {"status": value}

    return request, calls


def test_deploy_uses_actual_site_sha_and_uploaded_artifact_not_source_sha(
    capsys,
):
    request, calls = scripted_request(["deployment_queued", "succeed"])
    assert (
        DEPLOY(123, SHA, ENV, request=request, sleep=lambda _: None)
        == "https://fastfence.dev/"
    )
    assert calls[1] == (
        ENDPOINT,
        ENV["GITHUB_TOKEN"],
        {
            "data": {
                "artifact_id": 123,
                "pages_build_version": SHA,
                "oidc_token": "test-issued-oidc-secret",
            }
        },
    )
    assert calls[0][1] == ENV["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    assert calls[2][0] == ENDPOINT + "/" + SHA
    assert all(not call[0].endswith("/cancel") for call in calls)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "status",
    [
        "deployment_failed",
        "deployment_content_failed",
        "invented",
        None,
        {"token": "hidden"},
    ],
)
def test_failure_or_malformed_state_requests_cancellation(status):
    request, calls = scripted_request([status])
    with pytest.raises(ERROR):
        DEPLOY(123, SHA, ENV, request=request)
    assert calls[-1][0] == ENDPOINT + "/" + SHA + "/cancel"


def test_timeout_cancels_without_unbounded_polling():
    now = [0]
    request, calls = scripted_request(["deployment_queued"] * 5)

    def sleep(seconds):
        now[0] += seconds

    with pytest.raises(ERROR, match="timed out"):
        DEPLOY(
            123,
            SHA,
            ENV,
            request=request,
            clock=lambda: now[0],
            sleep=sleep,
            timeout=6,
        )
    assert now[0] == 6
    assert len(calls) == 5  # identity, create, two polls, cancel
    assert calls[-1][0].endswith("/cancel")


@pytest.mark.parametrize(
    "error", [ERROR("sanitized transport failure"), KeyboardInterrupt()]
)
def test_transport_failure_and_interrupt_cancel(error):
    request, calls = scripted_request([error])
    with pytest.raises(type(error)):
        DEPLOY(123, SHA, ENV, request=request)
    assert calls[-1][0].endswith("/cancel")


def test_server_status_url_is_never_followed():
    request, calls = scripted_request(
        ["succeed"], created={"status_url": "https://evil.invalid/steal"}
    )
    DEPLOY(123, SHA, ENV, request=request)
    assert calls[-1][0] == ENDPOINT + "/" + SHA


@pytest.mark.parametrize(
    "url",
    [
        "http://run.actions.githubusercontent.com/id",
        "https://evil.invalid/id",
        "https://actions.githubusercontent.com.evil.invalid/id",
        "https://user:password@run.actions.githubusercontent.com/id",  # pragma: allowlist secret - synthetic rejected URL
        "https://run.actions.githubusercontent.com:8443/id",
    ],
)
def test_oidc_bearer_is_not_sent_to_untrusted_endpoint(url):
    request, calls = scripted_request([])
    with pytest.raises(ERROR):
        DEPLOY(
            123,
            SHA,
            {**ENV, "ACTIONS_ID_TOKEN_REQUEST_URL": url},
            request=request,
        )
    assert calls == []


@pytest.mark.parametrize(
    ("artifact", "sha"), [(0, SHA), (True, SHA), (123, "main"), (123, "x" * 40)]
)
def test_invalid_identity_fails_before_network(artifact, sha):
    request, calls = scripted_request([])
    with pytest.raises(ERROR):
        DEPLOY(artifact, sha, ENV, request=request)
    assert calls == []


class Response(io.BytesIO):
    status = 200


def install_opener(monkeypatch, payload=None, error=None):
    class Opener:
        def open(self, request, **kwargs):
            if error:
                raise error
            return Response(payload)

    monkeypatch.setattr(
        SCRIPT["urllib"].request, "build_opener", lambda *args: Opener()
    )


@pytest.mark.parametrize(
    "payload", [b"[1]", b"not JSON", b"x" * (1024 * 1024 + 1)]
)
def test_bounded_transport_rejects_invalid_body(monkeypatch, payload):
    install_opener(monkeypatch, payload)
    with pytest.raises(ERROR):
        SCRIPT["request_json"]("https://api.github.com/test", "test-token")


def test_http_error_does_not_include_raw_provider_or_token(monkeypatch):
    install_opener(
        monkeypatch,
        error=urllib.error.HTTPError(
            "https://api.github.com/test?private=secret",
            302,
            "raw-secret-token",
            {},
            io.BytesIO(b"private payload"),
        ),
    )
    with pytest.raises(ERROR) as error:
        SCRIPT["request_json"]("https://api.github.com/test", "test-token")
    assert "secret" not in str(error.value)
    assert "private" not in str(error.value)
    assert error.value.http_status == 302
    assert "http_status=302" in error.value.diagnostic()
    assert (
        SCRIPT["NoRedirect"]().redirect_request(
            None, None, 302, "", {}, "https://evil.invalid"
        )
        is None
    )


@pytest.mark.parametrize("phase", ["oidc", "create", "poll"])
def test_failure_records_phase_and_http_status_without_payload(phase):
    ordinary, calls = scripted_request(["succeed"])
    failing_url = {
        "oidc": ENV["ACTIONS_ID_TOKEN_REQUEST_URL"],
        "create": ENDPOINT,
        "poll": ENDPOINT + "/" + SHA,
    }[phase]

    def request(url, token, **kwargs):
        if url == failing_url:
            raise ERROR("PRIVATE_SYNTHETIC_MESSAGE", http_status=403)
        return ordinary(url, token, **kwargs)

    with pytest.raises(ERROR) as caught:
        DEPLOY(123, SHA, ENV, request=request)
    assert caught.value.phase == phase
    assert caught.value.http_status == 403
    assert "PRIVATE" not in caught.value.diagnostic()
    if phase == "poll":
        assert calls[-1][0].endswith("/cancel")


@pytest.mark.parametrize(
    "status,expected",
    [
        ("deployment_content_failed", "deployment_content_failed"),
        ("", "empty"),
        ("PRIVATE_SYNTHETIC_STATUS", "invalid"),
    ],
)
def test_provider_diagnostics_only_allow_known_statuses(status, expected):
    request, _ = scripted_request([status])
    with pytest.raises(ERROR) as caught:
        DEPLOY(123, SHA, ENV, request=request)
    assert caught.value.phase == "poll"
    assert caught.value.provider_status == expected
    assert "PRIVATE" not in caught.value.diagnostic()


def test_main_retains_safe_phase_diagnostics_but_never_exception_message(
    monkeypatch, capsys
):
    def fail(*args, **kwargs):
        raise ERROR(
            "PRIVATE_SYNTHETIC_MESSAGE https://private.invalid/",
            phase="create",
            http_status=422,
        )

    monkeypatch.setitem(SCRIPT["main"].__globals__, "deploy", fail)
    monkeypatch.setattr(
        SCRIPT["sys"],
        "argv",
        ["deploy_pages.py", "--artifact-id", "123", "--pages-sha", SHA],
    )
    assert SCRIPT["main"]() == 1
    captured = capsys.readouterr()
    assert "phase=create" in captured.err and "http_status=422" in captured.err
    assert "PRIVATE" not in captured.err and "https://" not in captured.err
    assert captured.out == ""
