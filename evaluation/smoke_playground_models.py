"""Fixture-only Chromium regression; no gateway, credentials or inference."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from playwright.sync_api import expect, sync_playwright

from fastfence.modules.control.domain.models import Policy


def fixture_status(root):
    policy = Policy.model_validate(
        yaml.safe_load((root / "config/policy.hybrid.yaml").read_text())
    ).model_dump(mode="json")
    policy["models"] = {"qwen3:4b": {"roles": ["analyst"]}}
    return {
        "policy": policy,
        "feed": {"version": 1, "signatures": []},
        "runtime": {"instance_id": "explicit-ui-fixture"},
        "configuration": {
            "management_writable": True,
            "source_kind": "local_files",
            "generation": 1,
            "last_checked_at": "2099-01-01T00:00:00Z",
            "last_error": None,
        },
        "metrics": {
            "requests": 0,
            "blocked": 0,
            "redacted": 0,
            "p95_latency_ms": 0,
            "throughput_rps": 0,
            "semantic_calls": 0,
            "audit_retained": 0,
            "audit_dropped": 0,
        },
        "budgets": [],
        "audit": [],
        "semantic_status": "Explicit UI fixture; no semantic inference",
    }


def install_fixture(page, root, status, calls):
    web = root / "src/fastfence/app/interfaces/http/web"

    def serve(route):
        path = urlsplit(route.request.url).path
        if path == "/":
            route.fulfill(
                body=(web / "index.html").read_text(), content_type="text/html"
            )
        elif path.startswith("/assets/") and path.rsplit("/", 1)[1] in {
            "playground.js",
            "rules.js",
            "policy-studio.js",
            "audit.js",
            "documents.js",
            "console.js",
            "console.css",
            "policy-manager.js",
            "policy-panels.html",
            "logo.svg",
        }:
            suffix = Path(path).suffix
            route.fulfill(
                body=(web / path.rsplit("/", 1)[1]).read_text(),
                content_type={
                    ".js": "text/javascript",
                    ".css": "text/css",
                    ".html": "text/html",
                    ".svg": "image/svg+xml",
                }[suffix],
            )
        elif path == "/api/me":
            admin = (
                route.request.headers.get("authorization")
                == "Bearer fixture-admin"
            )
            route.fulfill(
                json={
                    "subject": "ui-fixture",
                    "tenant": "blue",
                    "roles": ["analyst"],
                    "admin": admin,
                }
            )
        elif path == "/api/admin/status":
            route.fulfill(json=status)
        elif path == "/api/models/complete":
            calls.append(route.request.post_data_json)
            route.fulfill(
                json={
                    "request_id": "ui-fixture-request",
                    "decision": "allowed",
                    "reason": "explicit_ui_fixture",
                    "policy_version": status["policy"]["version"],
                    "feed_version": 1,
                    "latency_ms": 0,
                    "upstream_executed": False,
                    "output": {"text": "fixture only"},
                    "findings": [],
                    "tokens": 0,
                }
            )
        else:
            route.fulfill(status=404, body="Unexpected fixture path")

    page.route("**/*", serve)


def run(root):
    status, calls = fixture_status(root), []
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda error: failures.append(str(error)))
        install_fixture(page, root, status, calls)
        page.goto("http://fastfence.fixture/")
        page.locator("#connectBtn").click()
        page.locator("#agentToken").fill("fixture-agent")
        page.locator("#adminToken").fill("fixture-admin")
        page.locator("#saveConnect").click()
        expect(page.locator("#connectDialog")).not_to_be_visible()
        page.locator('nav [data-nav="requests"]').click()
        expect(page.locator("#completionModel")).to_have_value("qwen3:4b")
        page.locator("#playgroundMode").select_option("model")
        expect(page.locator("#completionModel")).to_have_value("qwen3:4b")
        page.locator("#completionPrompt").fill("Keep this authored prompt")
        page.locator("#completionTokens").fill("7")
        page.locator("#invokeBtn").click()
        expect(page.locator("#result")).to_contain_text("explicit_ui_fixture")
        assert calls[0]["model"] == "qwen3:4b"

        status["policy"]["models"]["fixture:second"] = {"roles": ["analyst"]}
        page.evaluate("refresh()")
        page.locator("#completionModel").fill("fixture:second")
        page.locator("#completionPrompt").focus()
        page.evaluate("refresh()")
        expect(page.locator("#completionModel")).to_have_value("fixture:second")

        status["policy"]["models"] = {"qwen3:4b": {"roles": ["analyst"]}}
        page.evaluate("refresh()")
        expect(page.locator("#completionModel")).to_have_value("qwen3:4b")
        expect(page.locator("#completionPrompt")).to_have_value(
            "Keep this authored prompt"
        )
        expect(page.locator("#completionTokens")).to_have_value("7")

        page.locator("#completionModel").fill("being-edited")
        page.evaluate("refresh()")
        expect(page.locator("#completionModel")).to_have_value("being-edited")
        page.locator("#completionPrompt").focus()
        expect(page.locator("#completionModel")).to_have_value("qwen3:4b")

        status["policy"]["models"] = {}
        page.evaluate("refresh()")
        expect(page.locator("#completionModel")).to_have_value("")
        assert page.locator("#allowedModels option").count() == 0
        assert not failures, failures
        browser.close()
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "UI_contract_fixtures_only_no_inference",
        "all_passed": True,
        "checks": [
            "hybrid_default_selects_allowed_model",
            "submitted_model_matches_allowlist",
            "valid_selection_preserved",
            "removed_model_replaced",
            "prompt_and_token_inputs_preserved",
            "focused_model_edit_preserved_until_blur",
            "empty_allowlist_clears_selection",
        ],
        "fixture_completion_requests": len(calls),
        "actual_model_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(Path.cwd())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
