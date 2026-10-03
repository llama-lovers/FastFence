"""The advertised demo rejects unexpected controls, never dumping private bodies."""

import json

import httpx
import pytest

from examples.business_tools import verify as cli


def configure_demo(tmp_path, monkeypatch, mutate=None):
    tokens = {
        subject: subject
        for subject in ["analyst-blue", "operator-blue", "security-admin"]
    }
    (tmp_path / "demo-tokens.json").write_text(json.dumps(tokens))
    requests = []

    def respond(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "semantic_status": "disabled",
                    "metrics": {"requests": 7},
                },
            )
        body = json.loads(request.content)
        requests.append(body)
        arguments = body["arguments"]
        tool = body["tool"]
        if "Ignore all previous" in arguments.get("query", ""):
            expected = ("blocked", "attack_signature", False)
        elif "@" in arguments.get("query", ""):
            expected = ("blocked", "input_sensitive_data", False)
        elif (
            tool == "payments.prepare"
            and "analyst-blue" in request.headers["Authorization"]
        ):
            expected = ("blocked", "role_not_allowed", False)
        elif arguments.get("resource", "").startswith("green/"):
            expected = ("blocked", "cross_tenant_resource", False)
        elif tool == "report.contact":
            expected = ("redacted", "privacy_redacted", True)
        else:
            expected = ("allowed", "controls_passed", True)
        result = dict(
            zip(
                ["decision", "reason", "upstream_executed"],
                expected,
                strict=True,
            )
        )
        result["output"] = "PRIVATE_RESPONSE_CONTENT"
        if mutate and len(requests) == 1:
            return mutate(result)
        return httpx.Response(200, json=result)

    constructor = httpx.Client
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        cli.httpx,
        "Client",
        lambda **kwargs: constructor(**kwargs, transport=transport),
    )
    return requests


def test_demo_verifies_actual_api_engine_default_scenarios(
    client, project, monkeypatch, capsys
):
    constructor = httpx.Client
    responses = []

    def forward(request):
        response = client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=dict(request.headers),
            content=request.content,
        )
        responses.append(response)
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers=response.headers,
        )

    transport = httpx.MockTransport(forward)
    monkeypatch.setattr(
        cli.httpx,
        "Client",
        lambda **kwargs: constructor(**kwargs, transport=transport),
    )
    cli.demo(project / "state", "http://localhost")
    output = capsys.readouterr().out
    assert len(responses) == 8
    assert responses[-1].json()["metrics"]["requests"] == 7
    assert "Allowed business request: ALLOWED" in output
    assert "Sensitive output redacted: REDACTED" in output
    assert "anna@example.org" not in output


@pytest.mark.parametrize(
    "change",
    [
        {
            "decision": "blocked",
            "reason": "budget_calls",
            "upstream_executed": False,
        },
        {"upstream_executed": False},
        {"upstream_executed": 1},
        {"reason": "PRIVATE_RESPONSE_CONTENT"},
    ],
)
def test_unexpected_outcome_including_budget_denial_exits_nonzero_and_sanitized(
    tmp_path, monkeypatch, capsys, change
):
    def mutate(result):
        return httpx.Response(200, json={**result, **change})

    requests = configure_demo(tmp_path, monkeypatch, mutate)
    with pytest.raises(SystemExit, match="Allowed business request") as error:
        cli.demo(tmp_path, "http://localhost")
    assert error.value.code != 0
    assert len(requests) == 1
    assert "PRIVATE_RESPONSE_CONTENT" not in str(error.value)
    assert "PRIVATE_RESPONSE_CONTENT" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, text="PRIVATE_RESPONSE_CONTENT"),
        httpx.Response(200, text="PRIVATE_RESPONSE_CONTENT"),
        httpx.Response(200, json=[]),
    ],
)
def test_http_or_malformed_response_is_not_a_successful_demo(
    tmp_path, monkeypatch, response
):
    configure_demo(tmp_path, monkeypatch, lambda result: response)
    with pytest.raises(SystemExit, match="Demo failed") as error:
        cli.demo(tmp_path, "http://localhost")
    assert "PRIVATE_RESPONSE_CONTENT" not in str(error.value)
