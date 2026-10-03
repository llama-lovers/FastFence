"""Generic updates cannot overwrite source changes the poller has not seen."""

import yaml

from tests.fixtures.auth import headers


def test_unpolled_source_edit_rejects_generic_policy_put(
    client, app, project, tokens
):
    runtime = app.state.runtime
    base = runtime.snapshot().policy
    path = project / "config/policy.yaml"
    external = base.editable()
    external["version"] = base.version + 1
    external["semantic"]["threshold"] = 0.5
    content = yaml.safe_dump(external, sort_keys=False)
    path.write_text(content)

    stale_editor = base.editable()
    stale_editor["version"] = base.version + 1
    stale_editor["description"] = "Change from the stale editor"
    response = client.put(
        "/api/admin/policy",
        headers=headers(tokens, "security-admin"),
        json=stale_editor,
    )
    assert response.status_code == 409
    assert path.read_text() == content
    assert runtime.snapshot().policy == base
    assert not any(row["reason"] == "policy_saved" for row in runtime.audit())

    reloaded = client.post(
        "/api/admin/reload", headers=headers(tokens, "security-admin")
    )
    assert reloaded.status_code == 200
    assert runtime.snapshot().policy.semantic.threshold == 0.5
    reviewed = runtime.snapshot().policy.editable()
    reviewed["version"] += 1
    reviewed["description"] = "Reviewed against the external change"
    saved = client.put(
        "/api/admin/policy",
        headers=headers(tokens, "security-admin"),
        json=reviewed,
    )
    assert saved.status_code == 200
    assert runtime.snapshot().policy.semantic.threshold == 0.5
    assert yaml.safe_load(path.read_text()) == reviewed
