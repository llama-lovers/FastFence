"""Authoring safety with labeled draft fixtures; actual inference is checked separately."""

from __future__ import annotations

import argparse
import json
import stat

import httpx
import pytest

from integrations.laya import author_rule


def proposal():
    return {
        "id": "drafted-letter-a",
        "operator": "word_contains",
        "value": "a",
        "direction": "output",
        "target": "model",
        "action": "block",
        "case_sensitive": False,
    }


@pytest.mark.parametrize(
    "content",
    [
        "```json\n{}\n```",
        '{"supported":"true","rule":null}',
        '{"supported":true,"supported":false,"rule":null}',
        '{"supported":false,"rule":null}',
        '{"supported":true,"rule":null}',
        '{"supported":true,"rule":{},"private-extra":"private-marker"}',
        json.dumps(
            {"supported": True, "rule": {**proposal(), "direction": "both"}}
        ),
        json.dumps(
            {"supported": True, "rule": {**proposal(), "target": "all"}}
        ),
        "private-marker" * 2000,
    ],
)
def test_model_proposals_fail_closed_without_repair_or_scope_expansion(content):
    with pytest.raises(author_rule.AuthoringError) as error:
        author_rule.parse_proposal(content, "output", "model")
    assert "private-marker" not in str(error.value)


def test_valid_model_proposal_preserves_exact_rule():
    rule = proposal()
    envelope = json.dumps({"supported": True, "rule": rule})
    assert author_rule.parse_proposal(envelope, "output", "model") == rule


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://127.0.0.1.evil.example",
        "http://user:private@127.0.0.1",
        "http://127.0.0.1/path",
        "http://127.0.0.1?private=value",
        "http://127.0.0.1#private",
        "file:///tmp/local",
        "http://127.0.0.1:invalid",
    ],
)
def test_authoring_origins_cannot_redirect_trusted_credentials(url):
    with pytest.raises(argparse.ArgumentTypeError):
        author_rule.local_url(url)


@pytest.fixture
def management(tmp_path, monkeypatch):
    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"security-admin": "fixture-admin"}))
    args = argparse.Namespace(
        credentials=credentials,
        instruction="private instruction",
        proposal=None,
        save_proposal=None,
        direction="output",
        target="model",
        sample=["private sample"],
        activate=False,
        url="http://127.0.0.1:8000",
        ollama_url="http://127.0.0.1:11434",
        model="qwen3:4b",
        source=tmp_path,
        output=None,
    )
    state = {
        "policy": {
            "version": 11,
            "privacy": {"enabled": True},
            "text_rules": [],
        },
        "preview_rule": proposal(),
        "fail_path": None,
        "drafts": 0,
        "requests": [],
        "published": None,
    }

    async def draft_fixture(arguments, schema):
        state["drafts"] += 1
        return proposal(), 12

    def respond(request):
        state["requests"].append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer fixture-admin"
        if request.url.path == state["fail_path"]:
            return httpx.Response(409, json={"detail": "private server error"})
        if request.url.path == "/api/admin/rules/schema":
            return httpx.Response(200, json={"type": "object"})
        if request.url.path == "/api/admin/rules/preview":
            return httpx.Response(
                200, json={"rule": state["preview_rule"], "matches": [False]}
            )
        if request.url.path == "/api/admin/status":
            return httpx.Response(200, json={"policy": state["policy"]})
        assert (
            request.method == "PUT" and request.url.path == "/api/admin/policy"
        )
        state["published"] = json.loads(request.content)
        return httpx.Response(
            200, json={"policy_version": state["published"]["version"]}
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(respond), **kwargs
        ),
    )
    monkeypatch.setattr(author_rule, "draft", draft_fixture)
    return args, state


async def test_default_authoring_previews_without_mutation_and_report_omits_private_data(
    management,
):
    args, state = management
    report = await author_rule.author(args)
    assert not report.activated and report.policy_version == 11
    assert state["published"] is None and state["drafts"] == 1
    assert state["requests"] == [
        ("GET", "/api/admin/rules/schema"),
        ("POST", "/api/admin/rules/preview"),
        ("GET", "/api/admin/status"),
    ]
    serialized = report.model_dump_json()
    assert "private instruction" not in serialized
    assert "private sample" not in serialized
    assert "fixture-admin" not in serialized


async def test_explicit_activation_merges_into_latest_policy_preserving_other_controls(
    management,
):
    args, state = management
    args.activate = True
    existing = {**proposal(), "id": "existing", "value": "b"}
    state["policy"]["text_rules"] = [existing]
    original = json.loads(json.dumps(state["policy"]))
    report = await author_rule.author(args)
    assert report.activated and report.policy_version == 12
    assert state["published"] == {
        **original,
        "version": 12,
        "text_rules": [existing, proposal()],
    }
    assert state["policy"] == original


@pytest.mark.parametrize(
    "failure", ["noncanonical", "collision", "preview_http", "publish_http"]
)
async def test_management_rejections_never_publish_an_invalid_rule(
    management, failure
):
    args, state = management
    args.activate = True
    if failure == "noncanonical":
        state["preview_rule"] = {**proposal(), "value": "b"}
    elif failure == "collision":
        state["policy"]["text_rules"] = [proposal()]
    elif failure == "preview_http":
        state["fail_path"] = "/api/admin/rules/preview"
    else:
        state["fail_path"] = "/api/admin/policy"
    with pytest.raises(author_rule.AuthoringError) as error:
        await author_rule.author(args)
    assert "private server error" not in str(error.value)
    assert state["published"] is None
    attempted_puts = sum(method == "PUT" for method, path in state["requests"])
    assert attempted_puts == (1 if failure == "publish_http" else 0)


async def test_saved_reviewed_proposal_activates_exact_rule_without_repeating_inference(
    management, tmp_path
):
    args, state = management
    saved = tmp_path / "reviewed.json"
    author_rule.save_proposal(saved, proposal())
    args.proposal, args.instruction, args.activate = saved, None, True
    report = await author_rule.author(args)
    assert state["drafts"] == 0
    assert state["published"]["text_rules"] == [proposal()]
    assert report.authoring_source == "reviewed_proposal"
    assert report.model is None and report.inference_ms == 0
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600


async def test_saved_draft_is_private_exact_review_artifact_without_activation(
    management, tmp_path
):
    args, state = management
    args.save_proposal = tmp_path / "private/draft.json"
    await author_rule.author(args)
    assert json.loads(args.save_proposal.read_text()) == proposal()
    assert stat.S_IMODE(args.save_proposal.stat().st_mode) == 0o600
    assert state["published"] is None


def test_saving_review_artifact_rejects_symlinks_and_preserves_target(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("untouched")
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    with pytest.raises(OSError):
        author_rule.save_proposal(link, proposal())
    assert target.read_text() == "untouched"


@pytest.mark.parametrize(
    "extra_body", [{}, {"num_ctx": 8192, "reasoning_effort": "medium"}]
)
async def test_ollama_options_adapter_preserves_original_laya_call_and_metadata(
    extra_body,
):
    original_options = {
        "temperature": 0,
        "max_tokens": 1536,
        "response_format": {"type": "json_schema"},
        "extra_body": extra_body,
    }
    before = json.loads(json.dumps(original_options))
    metadata = {"provider": "fixture", "request_id": "original-request"}
    forwarded = []
    kwargs = {
        "role": "chat",
        "messages": [{"role": "user", "content": "ordinary instruction"}],
        "response_schema": {"type": "object"},
    }

    async def original_prepare(**options):
        forwarded.append(options)
        return "ollama/qwen3:4b", original_options, metadata

    (
        model,
        adapted,
        returned_metadata,
    ) = await author_rule.prepare_ollama_options(original_prepare, **kwargs)
    assert forwarded == [kwargs]
    assert model == "ollama/qwen3:4b" and returned_metadata is metadata
    assert adapted == {
        **before,
        "extra_body": {**before["extra_body"], "reasoning_effort": "none"},
    }
    assert original_options == before
    assert adapted is not original_options
    assert adapted["extra_body"] is not extra_body
