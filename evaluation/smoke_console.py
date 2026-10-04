"""Real Chromium console acceptance using explicit synthetic API fixtures only."""

import argparse
import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

if __package__:
    from evaluation.console_metrics_checks import metric_checks
    from evaluation.semantic_review_browser import (
        named_rule_checks,
        serve_semantic_fixture,
    )
    from evaluation.smoke_playground_models import fixture_status
else:
    from console_metrics_checks import metric_checks
    from semantic_review_browser import (
        named_rule_checks,
        serve_semantic_fixture,
    )
    from smoke_playground_models import fixture_status


class ConsoleFixture:
    def __init__(self, root):
        self.web = root / "src/fastfence/app/interfaces/http/web"
        self.status = fixture_status(root)
        self.status["policy"]["tools"] = {}
        self.status["policy"]["version"] = 1
        self.status["policy"]["text_rules"] = []
        self.status["policy"]["anonymization"] = {
            "mode": "irreversible",
            "rules": [],
        }
        self.status_error = False
        self.publish_error = False
        self.tests_passed = True
        self.semantic_preview_error = False
        self.semantic_decision = "blocked"
        self.semantic_previews = []
        self.writes = []
        self.requests = []
        self.rule = {
            "id": "no-letter-a",
            "operator": "word_contains",
            "value": "a",
            "direction": "input",
            "target": "model",
            "action": "block",
            "case_sensitive": False,
        }

    def proposal(self):
        return {
            "proposal_id": "synthetic-console-proposal",
            "base_version": self.status["policy"]["version"],
            "expires_at": "2099-01-01T00:00:00Z",
            "source": "explicit_browser_fixture",
            "model": "fixture-no-inference",
            "inference_ms": 0,
            "operations": [{"type": "upsert_text_rule", "rule": self.rule}],
            "changes": [
                {"path": "text_rules", "before": [], "after": [self.rule]}
            ],
            "warnings": [],
            "yaml_diff": "--- active\n+++ candidate\n+ value: a",
            "tests": [
                {
                    "label": "deny-match",
                    "text": "Cat",
                    "target": "model",
                    "direction": "input",
                    "expected_decision": "blocked",
                }
            ],
        }

    def preview(self, body):
        def compare(sample, index):
            before = {
                "index": index,
                "decision": "no_local_match",
                "reason": "fixture",
                "findings": [],
                "safe_text": sample["text"],
            }
            matched = "a" in sample["text"].lower()
            after = {
                **before,
                "decision": "blocked" if matched else "no_local_match",
                "safe_text": None if matched else sample["text"],
                "findings": ["no-letter-a"] if matched else [],
            }
            return {
                "index": index,
                "before": before,
                "after": after,
                "changed": matched,
                "safe_text_changed": matched,
            }

        pairs = [
            compare(item, i) for i, item in enumerate(body.get("samples", []))
        ]
        tests = [
            {
                "test": item,
                "comparison": compare(item, i),
                "passed": self.tests_passed,
            }
            for i, item in enumerate(body.get("tests", []))
        ]
        return {
            **self.proposal(),
            "results": [pair["after"] for pair in pairs],
            "comparisons": pairs,
            "test_results": tests,
            "tests_passed": self.tests_passed,
            "feed_version": 1,
        }

    def serve(self, route):
        request = route.request
        path = urlsplit(request.url).path
        self.requests.append((request.method, path))
        if self.serve_asset(route, path):
            return
        if serve_semantic_fixture(self, route, path):
            return
        if path == "/api/admin/semantic/preview":
            self.semantic_preview(route)
            return
        self.serve_api(route, path)

    def semantic_preview(self, route):
        body = route.request.post_data_json
        self.semantic_previews.append(body)
        if self.semantic_preview_error:
            route.fulfill(
                status=503,
                json={
                    "detail": "Laya text analysis is unavailable or busy. The rule was not activated; check setup and retry."
                },
            )
            return
        route.fulfill(
            json={
                "decision": self.semantic_decision,
                "semantic_score": 1
                if self.semantic_decision == "blocked"
                else 0,
                "provider": "laya",
                "model": "qwen3:4b",
                "rule_applied": True,
                "base_version": body["base_version"],
                "latency_ms": 12,
            }
        )

    def serve_asset(self, route, path):
        if path == "/":
            route.fulfill(
                body=(self.web / "index.html").read_text(),
                content_type="text/html",
            )
            return True
        if path.startswith("/assets/"):
            name = path.removeprefix("/assets/")
            asset = self.web / name
            if (
                "/" not in name
                and asset.is_file()
                and asset.suffix in {".js", ".css", ".html", ".svg"}
            ):
                route.fulfill(
                    body=asset.read_bytes(),
                    content_type={
                        ".js": "text/javascript",
                        ".css": "text/css",
                        ".html": "text/html",
                        ".svg": "image/svg+xml",
                    }[asset.suffix],
                )
                return True
        return False

    def identity(self, route):
        token = route.request.headers.get("authorization", "")
        if token not in {
            "Bearer fixture-agent",
            "Bearer fixture-admin",
            "Bearer fixture-other-agent",
        }:
            route.fulfill(status=401, json={"detail": "invalid_identity"})
        else:
            route.fulfill(
                json={
                    "subject": "other-agent"
                    if token.endswith("other-agent")
                    else "fixture-identity",
                    "tenant": "fixture",
                    "roles": ["analyst"],
                    "admin": token == "Bearer fixture-admin",
                }
            )

    def serve_api(self, route, path):
        request = route.request
        if path == "/api/me":
            self.identity(route)
        elif path == "/api/admin/status":
            if self.status_error:
                route.fulfill(
                    status=503, json={"detail": "fixture_status_unavailable"}
                )
            else:
                route.fulfill(json=self.status)
        elif path == "/api/admin/policies/draft":
            route.fulfill(json=self.proposal())
        elif path == "/api/admin/policies/preview":
            route.fulfill(json=self.preview(request.post_data_json))
        elif path == "/api/admin/policies/activate":
            self.activate(route, path)
        elif path == "/api/admin/policy" and request.method == "PUT":
            self.writes.append((path, request.post_data_json))
            if self.publish_error:
                route.fulfill(
                    status=409, json={"detail": "policy_version_must_increase"}
                )
            else:
                self.status["policy"] = copy.deepcopy(request.post_data_json)
                route.fulfill(
                    json={"policy_version": self.status["policy"]["version"]}
                )
        elif path == "/api/admin/reload":
            route.fulfill(
                json={"policy_version": self.status["policy"]["version"]}
            )
        else:
            route.fulfill(
                status=404, json={"detail": "unexpected_fixture_path"}
            )

    def activate(self, route, path):
        self.writes.append((path, route.request.post_data_json))
        if self.publish_error:
            route.fulfill(
                status=409, json={"detail": "policy_base_version_conflict"}
            )
        else:
            self.status["policy"]["version"] += 1
            self.status["policy"]["text_rules"] = [self.rule]
            route.fulfill(
                json={
                    "proposal_id": "synthetic-console-proposal",
                    "policy_version": self.status["policy"]["version"],
                    "operations": [],
                    "tests_saved": True,
                    "warnings": [],
                }
            )


def connect(page, agent="fixture-agent", admin="fixture-admin"):
    page.locator("#connectBtn").click()
    page.locator("#agentToken").fill(agent)
    page.locator("#adminToken").fill(admin)
    page.locator("#saveConnect").click()


def shell_checks(page, fixture, screenshots):
    page.goto("http://fastfence.fixture/")
    expect(page.locator('[data-page="overview"]')).to_be_visible()
    expect(page.locator("#onboarding")).to_be_visible()
    connect(page)
    expect(page.locator("#connectDialog")).not_to_be_visible()
    expect(page.locator("#agentToken")).to_have_value("")
    expect(page.locator("#adminToken")).to_have_value("")
    assert page.evaluate("localStorage.length + sessionStorage.length") == 0
    original_actor = page.locator("#actorLabel").text_content()
    connect(page, agent="fixture-other-agent", admin="invalid-fixture")
    expect(page.locator("#connectError")).not_to_be_empty()
    expect(page.locator("#actorLabel")).to_have_text(original_actor)
    page.locator("#closeConnect").click()
    for name in [
        "policies",
        "requests",
        "documents",
        "activity",
        "connection",
        "overview",
    ]:
        page.locator(f'nav [data-nav="{name}"]').click()
        expect(page.locator(f'[data-page="{name}"]')).to_be_visible()
        assert page.locator("[data-page]:visible").count() == 1
        expect(page.locator(f'nav [data-nav="{name}"]')).to_have_attribute(
            "aria-current", "page"
        )
        assert page.url.endswith("#" + name)
    page.locator('nav [data-nav="requests"]').click()
    expect(page.locator("#playgroundMode")).to_have_value("model")
    assert page.locator("[data-preset], [data-model-prompt]").count() == 0
    assert page.locator("#tool option").count() == 0
    page.locator("#completionPrompt").fill("My authored request")
    page.locator('nav [data-nav="activity"]').click()
    fixture.status_error = True
    page.locator("#refreshBtn").click()
    expect(page.locator("#globalMessage")).not_to_be_empty()
    expect(page.locator("#completionPrompt")).to_have_value(
        "My authored request"
    )
    fixture.status_error = False
    page.locator("#refreshBtn").click()
    page.locator('nav [data-nav="overview"]').click()
    if screenshots:
        page.screenshot(
            path=str(screenshots / "console-desktop.png"), full_page=True
        )
        page.screenshot(
            path=str(screenshots.parent / "console-overview.png"),
            full_page=True,
        )
        page.locator('nav [data-nav="policies"]').click()
        page.screenshot(
            path=str(screenshots.parent / "console-policies.png"),
            full_page=True,
        )
    page.set_viewport_size({"width": 390, "height": 844})
    for name in [
        "overview",
        "policies",
        "requests",
        "documents",
        "activity",
        "connection",
    ]:
        page.locator(f'nav [data-nav="{name}"]').click()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth"
        ), name
    if screenshots:
        page.screenshot(
            path=str(screenshots / "console-mobile.png"), full_page=True
        )
    page.set_viewport_size({"width": 1440, "height": 1000})


def policy_checks(page, fixture, screenshots):
    page.locator('nav [data-nav="policies"]').click()
    page.locator("#policyBtn").click()
    page.locator("#policyDescription").fill("Reviewed local configuration")
    expect(page.locator("#savePolicy")).to_be_disabled()
    page.locator("#policyReview").click()
    expect(page.locator("#policyReviewDiff")).to_contain_text(
        "Reviewed local configuration"
    )
    if screenshots:
        page.screenshot(
            path=str(screenshots.parent / "console-policy-dialog.png"),
            full_page=True,
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth"
        )
        page.screenshot(
            path=str(screenshots.parent / "console-policy-dialog-mobile.png"),
            full_page=True,
        )
        page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("#policyConfirm").check()
    expect(page.locator("#savePolicy")).to_be_enabled()
    page.locator("#policyDescription").fill("Changed after review")
    expect(page.locator("#savePolicy")).to_be_disabled()
    expect(page.locator("#policyConfirm")).not_to_be_checked()
    fixture.publish_error = True
    page.locator("#policyReview").click()
    page.locator("#policyConfirm").check()
    page.locator("#savePolicy").click()
    expect(page.locator("#policyMessage")).to_contain_text(
        "policy_version_must_increase"
    )
    expect(page.locator("#policyDescription")).to_have_value(
        "Changed after review"
    )
    expect(page.locator("#savePolicy")).to_be_disabled()
    assert fixture.status["policy"]["version"] == 1
    fixture.publish_error = False
    page.locator("#policyReview").click()
    page.locator("#policyConfirm").check()
    page.locator("#savePolicy").click()
    expect(page.locator("#policyMessage")).to_contain_text(
        "Policy v2 is active"
    )
    expect(page.locator("#headerVersion")).to_have_text("Policy v2")
    page.locator("#closePolicy").click()

    page.locator("#policyStudioBtn").click()
    page.locator("#policyInstruction").fill(
        "Block words containing a on model input only."
    )
    page.locator("#draftPolicy").click()
    expect(page.locator("#policyDraftSection")).to_be_visible()
    expect(page.locator("#policyEffects")).to_contain_text("model inputs")
    page.locator("#policySamples").fill("Hi\nCat")
    fixture.tests_passed = False
    page.locator("#previewPolicy").click()
    expect(page.locator("#policyRegressionResults")).to_contain_text("FAIL")
    page.locator("#policyReviewed").check()
    expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    fixture.tests_passed = True
    page.locator("#previewPolicy").click()
    expect(page.locator("#policyRegressionResults")).to_contain_text("PASS")
    expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    page.locator("#policyReviewed").check()
    expect(page.locator("#activatePolicyDraft")).to_be_enabled()
    page.locator("#policyTestCases textarea").first.fill("Changed sample")
    expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    expect(page.locator("#policyReviewed")).not_to_be_checked()
    page.locator("#policyTestCases textarea").first.fill("Cat")
    page.locator("#previewPolicy").click()
    expect(page.locator("#policyRegressionResults")).to_contain_text("PASS")
    page.locator("#policyReviewed").check()
    page.locator("#activatePolicyDraft").click()
    expect(page.locator("#policyStudioMessage")).to_contain_text(
        "Policy v3 is active"
    )
    expect(page.locator("#headerVersion")).to_have_text("Policy v3")
    page.locator("#closePolicyStudio").click()
    expect(page.locator("#policyInventory")).to_contain_text("no-letter-a")
    assert fixture.writes[-1][0] == "/api/admin/policies/activate"
    assert fixture.writes[-1][1] == {
        "proposal_id": "synthetic-console-proposal",
        "base_version": 2,
    }

    fixture.status["configuration"]["management_writable"] = False
    fixture.status["configuration"]["source_kind"] = "http_bundle"
    page.evaluate("refresh()")
    expect(page.locator("#policySource")).to_contain_text("read-only")
    expect(
        page.locator("#policyInventory").get_by_role("button", name="Edit rule")
    ).to_be_disabled()
    writes_before = len(fixture.writes)
    page.locator("#policyBtn").click()
    expect(page.locator("#policyMessage")).to_contain_text("Read-only")
    expect(page.locator("#policyReview")).to_be_disabled()
    expect(page.locator("#savePolicy")).to_be_disabled()
    page.locator("#closePolicy").click()
    assert len(fixture.writes) == writes_before
    page.locator('nav [data-nav="connection"]').click()
    page.locator("#disconnectBtn").click()
    expect(page.locator("#connectionStatus")).to_have_text("Not connected")
    expect(page.locator("#headerVersion")).to_have_text("Policy not loaded")
    page.reload()
    expect(page.locator("#connectionStatus")).to_have_text("Not connected")


def run(root, screenshots=None):
    fixture = ConsoleFixture(root)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", fixture.serve)
        shell_checks(page, fixture, screenshots)
        policy_checks(page, fixture, screenshots)
        named_rule_checks(page, fixture, screenshots)
        metric_checks(page, fixture, screenshots)
        assert not errors, errors
        browser.close()
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "all_passed": True,
        "mode": "real_chromium_synthetic_api_fixtures_no_inference",
        "checks": [
            "overview_all_decision_counters",
            "request_queue_current_counts_and_timeout",
            "request_queue_missing_invalid_and_zero_values",
            "request_queue_wait_in_verdict_and_audit",
            "request_queue_rejection_labels",
            "request_queue_stale_and_identity_reset",
            "request_level_path_percentages_not_call_ratio",
            "recent_denial_scope_and_safe_rendering",
            "metrics_stale_warning_and_identity_reset",
            "metrics_mobile_no_overflow",
            "navigation",
            "atomic_identity_connection",
            "memory_only_credentials",
            "model_first_no_demo_presets",
            "visible_refresh_failure",
            "authored_request_survives_refresh_failure",
            "mobile_no_page_overflow",
            "settings_review_before_publish",
            "settings_edit_invalidates_review",
            "failed_publish_preserves_authored_settings",
            "active_version_updates",
            "failed_regressions_block_activation",
            "generated_case_edit_invalidates_review",
            "exact_reviewed_proposal_activation",
            "read_only_remote_source",
            "disconnect_and_reload_clear_identity",
            "named_rule_provider_failure_preserves_draft",
            "named_rule_preview_scope_and_nonmutation",
            "named_rule_scope_edits_invalidate_preview",
            "named_rule_all_selected_scopes_reviewed",
            "named_rule_explicit_expected_outcomes_gate",
            "named_rule_receipt_only_activation_no_generic_put",
            "named_rule_saved_case_scopes_preserved",
            "named_rule_saved_replay_never_activates",
            "named_rule_review_without_raw_json",
            "named_rule_explicit_activation_preserves_instruction",
            "named_rule_edit_requires_new_test",
        ],
        "actual_model_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    report = run(Path.cwd(), args.screenshots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
