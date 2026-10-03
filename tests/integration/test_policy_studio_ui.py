"""Serve only the explicitly supported dashboard assets."""

import pytest


@pytest.mark.parametrize(
    "name", ["rules.js", "playground.js", "policy-studio.js"]
)
def test_dashboard_scripts_have_security_headers_and_expected_mime_type(
    client, name
):
    response = client.get("/assets/" + name)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("name", ["index.html", "routes.py", "unknown.js"])
def test_asset_route_cannot_read_unlisted_files(client, name):
    assert client.get("/assets/" + name).status_code == 404
