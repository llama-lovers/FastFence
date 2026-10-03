import copy
import json
import time

import pytest
import yaml

from fastfence.app.interfaces.http.authoring_process import PolicyAuthoringError
from tests.fixtures.auth import headers

EMAIL_OPERATION = {
    "type": "set_privacy_detector",
    "detector": "pii_email",
    "direction": "input",
    "action": "redact",
}


class FixtureAuthor:
    """Explicit inference fixture; real Laya is covered by the separate live run."""

    def __init__(self, operation=EMAIL_OPERATION):
        self.operation = operation
        self.calls = 0
        self.failure = None
        self.envelope = None

    async def draft(self, request):
        self.calls += 1
        if self.failure:
            raise self.failure
        return {
            "source": "real_laya",
            "model": "qwen3:4b",
            "inference_ms": 1,
            "proposal": self.envelope
            or {
                "supported": True,
                "operations": [copy.deepcopy(self.operation)],
            },
        }


@pytest.fixture
def author(app):
    author = FixtureAuthor()
    app.state.policy_authoring.author = author
    return author


def draft(client, tokens, instruction="Redact emails in input", version=1):
    return client.post(
        "/api/admin/policies/draft",
        headers=headers(tokens, "security-admin"),
        json={"instruction": instruction, "base_version": version},
    )


def preview(client, tokens, proposal, samples=None):
    return client.post(
        "/api/admin/policies/preview",
        headers=headers(tokens, "security-admin"),
        json={"proposal_id": proposal["proposal_id"], "samples": samples or []},
    )


def activate(client, tokens, proposal, **extra):
    return client.post(
        "/api/admin/policies/activate",
        headers=headers(tokens, "security-admin"),
        json={
            "proposal_id": proposal["proposal_id"],
            "base_version": proposal["base_version"],
            **extra,
        },
    )


@pytest.mark.parametrize(
    "path,payload",
    [
        ("draft", {"instruction": "redact email", "base_version": 1}),
        ("preview", {"proposal_id": "x" * 24}),
        ("activate", {"proposal_id": "x" * 24, "base_version": 1}),
    ],
)
def test_authoring_endpoints_require_management_credentials(
    client, tokens, author, path, payload
):
    url = f"/api/admin/policies/{path}"
    assert client.post(url, json=payload).status_code == 401
    assert (
        client.post(url, json=payload, headers=headers(tokens)).status_code
        == 403
    )
    assert author.calls == 0


def test_draft_preview_and_exact_activation_use_one_inference(
    client, tokens, app, author
):
    before = app.state.runtime.snapshot()
    response = draft(client, tokens)
    assert response.status_code == 200, response.text
    proposal = response.json()
    assert proposal["operations"] == [EMAIL_OPERATION]
    assert app.state.runtime.snapshot() is before
    samples = [
        {"target": "model", "direction": "input", "text": "anna@example.org"}
    ]
    response = preview(client, tokens, proposal, samples)
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["decision"] == "redacted"
    assert "anna@example.org" not in response.json()["results"][0]["safe_text"]
    assert "authorization" in response.json()["scope"]
    assert author.calls == 1
    published = activate(client, tokens, proposal)
    assert published.status_code == 200, published.text
    assert published.json()["policy_version"] == 2
    assert author.calls == 1
    assert activate(client, tokens, proposal).status_code == 409


def test_activation_requires_backend_preview_and_refuses_client_edits(
    client, tokens, app, author
):
    proposal = draft(client, tokens).json()
    assert (
        activate(client, tokens, proposal).json()["detail"]
        == "proposal_preview_required"
    )
    preview(client, tokens, proposal)
    assert (
        activate(
            client, tokens, proposal, operations=[{"type": "anything"}]
        ).status_code
        == 422
    )
    assert app.state.runtime.snapshot().policy.version == 1


def test_selective_email_change_does_not_relax_secret_or_identifier_controls(
    client, tokens, app, author
):
    proposal = draft(client, tokens).json()
    preview(client, tokens, proposal)
    assert activate(client, tokens, proposal).status_code == 200

    def invoke(query):
        return client.post(
            "/api/invoke",
            headers=headers(tokens),
            json={"tool": "knowledge.search", "arguments": {"query": query}},
        ).json()

    assert invoke("anna@example.org")["decision"] == "redacted"
    blocked = invoke("anna@example.org and 12345678901")
    assert blocked["decision"] == "blocked" and not blocked["upstream_executed"]
    assert app.state.runtime.snapshot().policy.privacy.input == "block"


def test_restricted_tool_roles_enforce_before_upstream(
    client, tokens, app, author
):
    author.operation = {
        "type": "restrict_tool_roles",
        "tool": "knowledge.search",
        "roles": ["operator"],
    }
    proposal = draft(
        client, tokens, "Only operators may search knowledge"
    ).json()
    preview(client, tokens, proposal)
    assert activate(client, tokens, proposal).status_code == 200
    payload = {
        "tool": "knowledge.search",
        "arguments": {"query": "Quarterly forecast"},
    }
    denied = client.post(
        "/api/invoke", headers=headers(tokens), json=payload
    ).json()
    assert (
        denied["reason"] == "role_not_allowed"
        and not denied["upstream_executed"]
    )
    allowed = client.post(
        "/api/invoke", headers=headers(tokens, "operator-blue"), json=payload
    ).json()
    assert allowed["decision"] == "allowed"


def test_expired_stale_and_foreign_proposals_cannot_activate(
    client, tokens, app, author
):
    proposal = draft(client, tokens).json()
    record = app.state.policy_authoring._proposals[proposal["proposal_id"]]
    record.subject = "other-admin"
    assert preview(client, tokens, proposal).status_code == 404
    record.subject = "security-admin"
    record.expires_monotonic = time.monotonic() - 1
    assert preview(client, tokens, proposal).status_code == 410
    proposal = draft(client, tokens).json()
    preview(client, tokens, proposal)
    policy = app.state.runtime.snapshot().policy.editable()
    policy["version"] = 2
    assert (
        client.put(
            "/api/admin/policy",
            headers=headers(tokens, "security-admin"),
            json=policy,
        ).status_code
        == 200
    )
    assert activate(client, tokens, proposal).status_code == 409


@pytest.mark.parametrize(
    "envelope",
    [
        {"supported": False, "operations": []},
        {
            "supported": True,
            "operations": [
                {
                    "type": "restrict_tool_roles",
                    "tool": "payments.prepare",
                    "roles": ["analyst"],
                }
            ],
        },
        {
            "supported": True,
            "operations": [
                {
                    "type": "set_privacy_detector",
                    "detector": "invented",
                    "direction": "input",
                    "action": "redact",
                }
            ],
        },
    ],
)
def test_untrusted_or_unsupported_model_output_keeps_last_good_policy(
    client, tokens, app, author, envelope
):
    author.envelope = envelope
    before = app.state.runtime.snapshot()
    assert draft(client, tokens).status_code == 422
    assert app.state.runtime.snapshot() is before


def test_model_failure_is_sanitized_and_keeps_last_good_policy(
    client, tokens, app, author
):
    author.failure = RuntimeError(
        "private instruction and provider credentials"
    )
    response = draft(client, tokens)
    assert response.status_code == 503
    assert response.json()["detail"] == "laya_authoring_failed"
    assert "private instruction" not in response.text
    assert app.state.runtime.snapshot().policy.version == 1
    author.failure = PolicyAuthoringError("authoring_busy_try_again", 429)
    assert draft(client, tokens).status_code == 429


@pytest.mark.parametrize("instruction", [" ", "x" * 8193, "ą" * 4097])
def test_instruction_boundaries_reject_before_inference(
    client, tokens, author, instruction
):
    assert draft(client, tokens, instruction).status_code == 422
    assert author.calls == 0


def test_preview_sample_bounds_and_stale_draft_prevent_inference(
    client, tokens, author
):
    assert draft(client, tokens, version=9).status_code == 409
    assert author.calls == 0
    proposal = draft(client, tokens).json()
    assert (
        preview(client, tokens, proposal, [{"text": "a" * 4097}]).status_code
        == 422
    )
    assert (
        preview(client, tokens, proposal, [{"text": "tiny"}] * 17).status_code
        == 422
    )


def test_feed_only_update_requires_a_fresh_preview_before_exact_activation(
    client, tokens, app, project, author
):
    proposal = draft(client, tokens).json()
    assert preview(client, tokens, proposal).status_code == 200
    path = project / "config/signatures.json"
    feed = json.loads(path.read_text())
    feed["version"] += 1
    path.write_text(json.dumps(feed))
    assert (
        client.post(
            "/api/admin/reload", headers=headers(tokens, "security-admin")
        ).status_code
        == 200
    )
    denied = activate(client, tokens, proposal)
    assert denied.status_code == 409
    assert denied.json()["detail"] == "proposal_feed_changed_preview_again"
    assert app.state.runtime.snapshot().policy.version == 1
    assert preview(client, tokens, proposal).status_code == 200
    assert activate(client, tokens, proposal).status_code == 200


def test_bounded_proposal_store_rejects_capacity_before_another_inference(
    client, tokens, app, author
):
    app.state.policy_authoring.limit = 1
    assert draft(client, tokens).status_code == 200
    assert draft(client, tokens).status_code == 429
    assert author.calls == 1


def test_unseen_feed_file_change_cannot_bypass_activation_compare_and_swap(
    client, tokens, app, project, author
):
    proposal = draft(client, tokens).json()
    assert preview(client, tokens, proposal).status_code == 200
    before = app.state.runtime.snapshot()
    path = project / "config/signatures.json"
    feed = json.loads(path.read_text())
    feed["version"] += 1
    path.write_text(json.dumps(feed))
    # No reload: memory still matches the preview, but save reads the new feed.
    assert app.state.runtime.snapshot() is before
    denied = activate(client, tokens, proposal)
    assert denied.status_code == 409
    assert denied.json()["detail"] == "policy_activation_conflict"
    assert app.state.runtime.snapshot() is before
    assert app.state.runtime.snapshot().policy.privacy.input == "block"


@pytest.mark.parametrize("version", [1, 2])
def test_unseen_source_policy_edit_cannot_be_overwritten_by_authoring(
    client, tokens, app, project, author, version
):
    proposal = draft(client, tokens).json()
    assert preview(client, tokens, proposal).status_code == 200
    before = app.state.runtime.snapshot()
    path = project / "config/policy.yaml"
    changed = before.policy.editable()
    changed["description"] = "Operator changed this outside the gateway"
    changed["version"] = version
    path.write_text(yaml.safe_dump(changed))
    denied = activate(client, tokens, proposal)
    assert denied.status_code == 409
    assert denied.json()["detail"] == "policy_activation_conflict"
    assert app.state.runtime.snapshot() is before
    assert (
        yaml.safe_load(path.read_text())["description"]
        == changed["description"]
    )


def test_invalid_unseen_source_blocks_authoring_but_manual_repair_remains_available(
    client, tokens, app, project, author
):
    proposal = draft(client, tokens).json()
    assert preview(client, tokens, proposal).status_code == 200
    path = project / "config/policy.yaml"
    path.write_text("version: 9\nunknown: invalid\n")
    assert activate(client, tokens, proposal).status_code == 409
    candidate = app.state.runtime.snapshot().policy.editable()
    candidate["version"] = 2
    assert (
        client.put(
            "/api/admin/policy",
            headers=headers(tokens, "security-admin"),
            json=candidate,
        ).status_code
        == 200
    )
    assert yaml.safe_load(path.read_text())["version"] == 2
