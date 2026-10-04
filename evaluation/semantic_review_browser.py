"""Reviewed semantic authoring in Chromium, using explicit non-inference fixtures."""

import copy

from playwright.sync_api import expect


def serve_semantic_fixture(fixture, route, path):
    if path not in {
        "/api/admin/semantic/tests",
        "/api/admin/semantic/review",
        "/api/admin/semantic/activate",
        "/api/admin/semantic/tests/replay",
    }:
        return False
    if not hasattr(fixture, "semantic_suites"):
        fixture.semantic_suites = []
    if path.endswith("/tests"):
        route.fulfill(
            json={
                "schema_version": 1,
                "suite_digest": "fixture-digest",
                "policy_version": fixture.status["policy"]["version"],
                "suites": fixture.semantic_suites,
            }
        )
        return True
    body = route.request.post_data_json
    if path.endswith("/review"):
        fixture.semantic_previews.append(body)
        if fixture.semantic_preview_error:
            route.fulfill(
                status=503, json={"detail": "Laya is unavailable or busy"}
            )
            return True
        candidate = copy.deepcopy(fixture.status["policy"])
        candidate["version"] += 1
        candidate["semantic"].update(
            provider="laya", model="qwen3:4b", scan_output=True
        )
        candidate["semantic"]["rules"] = [body["rule"]]
        fixture.semantic_candidate = candidate
        fixture.semantic_review_body = body
        rows = []
        for item in body["cases"]:
            actual = (
                item["expected"]
                if fixture.tests_passed
                else "no_semantic_block"
            )
            rows.append(
                {
                    **item,
                    "rule_id": body["rule"]["id"],
                    "before": {
                        "status": "evaluated",
                        "decision": "no_semantic_block",
                        "latency_ms": 2,
                        "reason": None,
                    },
                    "after": {
                        "status": "evaluated",
                        "decision": actual,
                        "latency_ms": 3,
                        "reason": None,
                    },
                    "passed": actual == item["expected"],
                }
            )
        route.fulfill(
            json={
                "scope": "semantic_only",
                "review_id": "fixture-review" if fixture.tests_passed else None,
                "base_version": body["base_version"],
                "candidate_version": candidate["version"],
                "feed_version": fixture.status["feed"]["version"],
                "expires_at": "2099-01-01T00:00:00Z"
                if fixture.tests_passed
                else None,
                "model": "explicit-fixture-no-inference",
                "yaml_diff": "--- active\n+++ candidate\n+ "
                + body["rule"]["instruction"],
                "cases": rows,
                "tests_passed": fixture.tests_passed,
                "warnings": [],
                "missing_rules": [],
            }
        )
    elif path.endswith("/activate"):
        assert (
            body["confirmed"] is True and body["review_id"] == "fixture-review"
        )
        fixture.writes.append((path, body))
        fixture.status["policy"] = fixture.semantic_candidate
        request = fixture.semantic_review_body
        fixture.semantic_suites = [
            {
                "rule": request["rule"],
                "status": "current",
                "cases": [
                    {**item, "rule_id": request["rule"]["id"]}
                    for item in request["cases"]
                ],
            }
        ]
        route.fulfill(
            json={
                "review_id": body["review_id"],
                "policy_version": fixture.status["policy"]["version"],
                "feed_version": fixture.status["feed"]["version"],
                "tests_saved": True,
                "warnings": [],
            }
        )
    else:
        rows = [
            {
                **{
                    key: item[key]
                    for key in (
                        "id",
                        "rule_id",
                        "direction",
                        "target",
                        "expected",
                    )
                },
                "status": "evaluated",
                "decision": item["expected"],
                "latency_ms": 3,
                "reason": None,
                "passed": True,
            }
            for suite in fixture.semantic_suites
            for item in suite["cases"]
        ]
        route.fulfill(
            json={
                "scope": "semantic_only",
                "policy_version": fixture.status["policy"]["version"],
                "suite_digest": "fixture-digest",
                "results": rows,
                "tests_passed": bool(rows),
                "skipped": [],
                "warnings": [],
            }
        )
    return True


def named_rule_checks(page, fixture, screenshots):
    fixture.status["configuration"].update(
        management_writable=True, source_kind="local_files"
    )
    page.locator("#connectBtn").click()
    page.locator("#agentToken").fill("fixture-agent")
    page.locator("#adminToken").fill("fixture-admin")
    page.locator("#saveConnect").click()
    expect(page.locator("#connectDialog")).not_to_be_visible()
    page.locator('nav [data-nav="policies"]').click()
    page.locator("#layaRuleBtn").click()
    instruction = "Block personalized investment recommendations. Allow general financial education."
    page.locator("#layaRuleId").fill("no-personal-investment-advice")
    page.locator("#layaRuleInstruction").fill(instruction)
    page.locator("#layaRuleBlockSamples").fill(
        "Tell me which stock I should buy."
    )
    page.locator("#layaRulePermitSamples").fill(
        "Explain portfolio diversification."
    )
    expect(page.locator("#layaRuleCallCount")).to_contain_text(
        "8 submitted scoped cases"
    )
    expect(page.locator("#activateLayaRule")).to_be_disabled()
    before = copy.deepcopy(fixture.status["policy"])
    writes = len(fixture.writes)
    fixture.semantic_preview_error = True
    page.locator("#layaRuleTest").click()
    expect(page.locator("#layaRuleMessage")).to_contain_text(
        "unavailable or busy"
    )
    expect(page.locator("#layaRuleInstruction")).to_have_value(instruction)
    expect(page.locator("#activateLayaRule")).to_be_disabled()
    fixture.semantic_preview_error = False
    fixture.tests_passed = False
    page.locator("#layaRuleTest").click()
    expect(page.locator("#layaRuleTestResult")).to_contain_text(
        "Some expectations failed"
    )
    page.locator("#layaRuleConfirmed").check()
    expect(page.locator("#activateLayaRule")).to_be_disabled()
    fixture.tests_passed = True
    page.locator("#layaRuleTest").click()
    expect(page.locator("#layaRuleTestResult")).to_contain_text(
        "All reviewed expectations passed"
    )
    submitted = fixture.semantic_previews[-1]["cases"]
    assert len(submitted) == 8
    assert {(item["direction"], item["target"]) for item in submitted} == {
        ("input", "model"),
        ("input", "tool"),
        ("output", "model"),
        ("output", "tool"),
    }
    expect(page.locator("#layaRuleResults tr")).to_have_count(8)
    expect(page.locator("#activateLayaRule")).to_be_disabled()
    assert fixture.status["policy"] == before and len(fixture.writes) == writes
    page.locator("#layaRuleConfirmed").check()
    expect(page.locator("#activateLayaRule")).to_be_enabled()
    page.locator("#layaRuleDirection").select_option("input")
    expect(page.locator("#activateLayaRule")).to_be_disabled()
    expect(page.locator("#layaRuleConfirmed")).not_to_be_checked()
    page.locator("#layaRuleTarget").select_option("model")
    page.locator("#layaRuleTest").click()
    expect(page.locator("#layaRuleResults tr")).to_have_count(2)
    page.locator("#layaRuleConfirmed").check()
    if screenshots:
        page.screenshot(
            path=str(screenshots / "semantic-reviewed-desktop.png"),
            full_page=True,
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth"
        )
        page.screenshot(
            path=str(screenshots / "semantic-reviewed-mobile.png"),
            full_page=True,
        )
        page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("#activateLayaRule").click()
    expect(page.locator("#layaRuleMessage")).to_contain_text(
        "Policy v4 is active"
    )
    assert fixture.writes[-1][0] == "/api/admin/semantic/activate"
    assert all(
        path != "/api/admin/policy" for path, _ in fixture.writes[writes:]
    )
    page.locator("#closeLayaRule").click()
    card = page.locator("#policyInventory .rule-card").filter(
        has_text="no-personal-investment-advice"
    )
    card.get_by_role("button", name="Edit rule", exact=True).click()
    expect(page.locator("#layaRuleInstruction")).to_have_value(instruction)
    expect(page.locator("#layaRuleSavedCases")).to_contain_text(
        "Saved expectations loaded with their exact scopes"
    )
    expect(page.locator("#layaRuleNewCases")).not_to_be_visible()
    expect(page.locator("#activateLayaRule")).to_be_disabled()
    page.locator("#closeLayaRule").click()
    page.locator("#replaySemanticTestsBtn").click()
    expect(page.locator("#semanticReplayMessage")).to_contain_text(
        "2 saved scoped cases"
    )
    writes = len(fixture.writes)
    page.locator("#runSemanticReplay").click()
    expect(page.locator("#semanticReplayMessage")).to_contain_text(
        "All evaluated expectations passed"
    )
    expect(page.locator("#semanticReplayResults")).to_contain_text("PASS")
    assert len(fixture.writes) == writes
    assert page.evaluate("localStorage.length + sessionStorage.length") == 0
    page.locator("#closeSemanticReplay").click()
