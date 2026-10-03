"""Browser audit-investigation fixtures; no model inference or production data."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

if __package__:
    from evaluation.smoke_playground_models import (
        fixture_status,
        install_fixture,
    )
else:
    from smoke_playground_models import fixture_status, install_fixture


def record(request_id, decision, reason, findings, executed):
    return {
        "request_id": request_id,
        "time": "2026-10-03T12:00:00Z",
        "subject": "analyst-blue",
        "tenant": "blue",
        "target": "qwen3:0.6b",
        "decision": decision,
        "reason": reason,
        "findings": findings,
        "upstream_executed": executed,
        "policy_version": 3,
        "feed_version": 2,
        "latency_ms": 4,
        "instance_id": "fixture-instance",
        "event_kind": "invocation",
        "semantic_score": None,
        "tokens": 42 if executed else 0,
        "prompt": "UNEXPECTED_BODY_MUST_NOT_RENDER",
    }


def run(root):
    status = fixture_status(root)
    status["audit"] = [
        record(
            "request-blocked",
            "blocked",
            "input_text_rule",
            ["ban-letter-a"],
            False,
        ),
        record(
            "request-redacted",
            "redacted",
            "privacy_redacted",
            ["pii_email"],
            True,
        ),
        record("request-allowed", "allowed", "controls_passed", [], True),
    ]
    status["audit"][0]["target"] = "<img src=x onerror=alert(1)>"
    errors, requests = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        install_fixture(page, root, status, [])
        page.goto("http://fastfence.fixture/")
        page.locator("#connectBtn").click()
        page.locator("#agentToken").fill("fixture-agent")
        page.locator("#adminToken").fill("fixture-admin")
        page.locator("#saveConnect").click()
        expect(page.locator("#connectDialog")).not_to_be_visible()
        page.locator('nav [data-nav="activity"]').click()
        expect(page.locator("#auditWindow")).to_contain_text("Showing 3 of 3")
        page.locator("#auditDecision").select_option("allowed")
        expect(page.locator("#events button")).to_have_count(1)
        expect(
            page.get_by_role("button", name="Inspect request request-allowed")
        ).to_be_visible()
        page.locator("#auditDecision").select_option("error")
        expect(page.locator("#events")).to_contain_text(
            "No loaded events match"
        )
        page.locator("#auditDecision").select_option("blocked")
        expect(page.locator("#events button")).to_have_count(1)
        page.locator("#auditSearch").fill("ban-letter-a")
        page.get_by_role(
            "button", name="Inspect request request-blocked"
        ).click()
        expect(page.locator("#audit-detail-0")).to_be_visible()
        expect(page.locator("#audit-detail-0")).to_contain_text(
            "Request ID: request-blocked"
        )
        expect(page.locator("#audit-detail-0")).to_contain_text(
            "Matched controls: ban-letter-a"
        )
        expect(page.locator("#audit-detail-0")).to_contain_text(
            "Upstream: Not executed"
        )
        expect(page.locator("#audit-detail-0")).to_contain_text("v3 / v2")
        assert page.locator("#events img").count() == 0
        assert (
            "UNEXPECTED_BODY_MUST_NOT_RENDER"
            not in page.locator("#events").inner_text()
        )
        page.evaluate("refresh()")
        expect(page.locator("#audit-detail-0")).to_be_visible()

        page.locator("#auditSearch").fill("private-search-needle")
        expect(page.locator("#events")).to_contain_text(
            "No loaded events match"
        )
        assert not any("private-search-needle" in url for url in requests)
        page.locator("#clearAuditFilters").click()
        expect(page.locator("#events button")).to_have_count(3)
        page.locator("#auditDecision").select_option("redacted")
        expect(page.locator("#events button")).to_have_count(1)

        page.evaluate(
            "record => renderVerdict({...record, output:null})",
            status["audit"][0],
        )
        page.locator('nav [data-nav="requests"]').click()
        page.get_by_role("button", name="Inspect in Activity →").click()
        expect(page.locator("#auditSearch")).to_have_value("request-blocked")
        expect(page.locator("#auditDecision")).to_have_value("")
        expect(page.locator("#audit-detail-0")).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        page.locator("#clearAuditFilters").click()
        status["audit"] = []
        page.evaluate("refresh()")
        expect(page.locator("#events")).to_contain_text("No decisions yet")
        assert not errors, errors
        browser.close()
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "UI_contract_fixtures_only_no_inference",
        "all_passed": True,
        "checks": [
            "request_and_rule_correlation",
            "decision_filter",
            "local_search",
            "expanded_record_survives_refresh",
            "untrusted_metadata_is_text",
            "unexpected_payload_fields_not_rendered",
            "verdict_links_to_audit",
            "bounded_window_and_empty_state",
            "mobile_no_page_overflow",
        ],
        "actual_model_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(Path.cwd())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
