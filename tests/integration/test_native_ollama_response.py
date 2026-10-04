"""The reported chat-provider failure must never become an HTTP success."""

import httpx

from tests.fixtures.auth import headers
from tests.fixtures.requests import chat_request


def test_incomplete_native_chat_is_503_without_reply(
    client, tokens, monkeypatch
):
    client_class = httpx.AsyncClient
    attempted = []

    def respond(request):
        attempted.append(request.url.path)
        return httpx.Response(
            200, json={"message": {"content": "Hello from upstream"}}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    response = client.post(
        "/v1/chat/completions", headers=headers(tokens), json=chat_request()
    )
    assert attempted == ["/api/chat"]
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable_fail_closed"
    assert "Hello from upstream" not in response.text
    assert response.headers["X-FastFence-Upstream-Executed"] == "true"
