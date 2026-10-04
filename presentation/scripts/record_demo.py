"""Record real FastFence UI operations in an explicitly isolated installation.

Requires playwright and ffmpeg; no API fixtures or product source imports.
The gateway and its disposable policy are supplied by the caller. Never point
this script at an operator's installation: it activates two demonstration rules.
"""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from video_export import export_video


def record(args):
    credentials = json.loads(args.credentials.read_text())
    target = args.output.resolve()
    assets = args.assets.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    captions, results = [], {}
    with tempfile.TemporaryDirectory(prefix="fastfence-demo-video-") as folder:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1600, "height": 900},
                record_video_dir=folder,
                record_video_size={"width": 1600, "height": 900},
            )
            started = time.monotonic()
            page = context.new_page()
            page.set_default_timeout(120_000)
            response = context.request.get(args.url + "/openapi.json")
            assert response.json()["info"]["version"] == "1.0.7"
            page.goto(args.url, wait_until="networkidle")
            page.locator("#connectBtn").click()
            page.locator("#agentToken").fill(credentials[args.agent_key])
            page.locator("#adminToken").fill(credentials[args.admin_key])
            page.locator("#saveConnect").click()
            expect(page.locator("#connectDialog")).not_to_be_visible()
            expect(page.locator("#headerVersion")).to_contain_text("Policy v")
            expect(page.locator("#agentToken")).to_have_value("")
            expect(page.locator("#adminToken")).to_have_value("")
            initial = page.evaluate("latestStatus")
            assert not any(
                rule["id"] == "demo-block-hello"
                for rule in initial["policy"].get("text_rules", [])
            )
            assert not initial["policy"]["semantic"].get("rules")
            instance = initial["runtime"]["instance_id"]
            trim = time.monotonic() - started
            origin = time.monotonic()

            def mark(message):
                captions.append((time.monotonic() - origin, message))

            def hold(seconds):
                page.wait_for_timeout(seconds * 1000)

            def shot(name):
                page.screenshot(path=str(assets / ("demo-" + name + ".png")))

            def nav(name):
                page.locator(f'nav [data-nav="{name}"]').click()
                page.evaluate("window.scrollTo(0, 0)")

            mark(
                "FastFence 1.0.7 | Live public package. Real Laya + local Qwen."
            )
            shot("overview")
            hold(6)
            nav("requests")
            mark(
                "1. Send a real model request through the active security policy."
            )
            page.locator("#completionModel").fill(args.model)
            page.locator("#completionTokens").fill("32")
            page.locator("#completionPrompt").press_sequentially(
                "Hello", delay=120
            )
            hold(2)
            with page.expect_response("**/api/models/complete") as response:
                page.locator("#invokeBtn").click()
            allowed = response.value.json()
            assert allowed["decision"] == "allowed", allowed["reason"]
            assert allowed["upstream_executed"]
            assert allowed["semantic_input_status"] == "passed"
            assert allowed["semantic_output_status"] == "passed"
            expect(page.locator("#result")).to_contain_text("ALLOWED")
            results["baseline"] = {
                key: allowed[key]
                for key in (
                    "decision",
                    "upstream_executed",
                    "semantic_input_status",
                    "semantic_output_status",
                    "policy_version",
                    "latency_ms",
                )
            }
            mark(
                "ALLOWED: Laya inspected input and output; the business model really ran."
            )
            shot("allowed")
            hold(8)
            nav("policies")
            page.locator("#textRuleBtn").click()
            mark(
                "2. Add a fast input rule. Test prohibited and permitted examples first."
            )
            page.locator("#textRuleId").fill("demo-block-hello")
            page.locator("#textRuleValue").press_sequentially(
                "Hello", delay=100
            )
            page.locator("#textRuleSamples").fill("Hello\nGood morning")
            hold(3)
            page.locator("#previewTextRule").click()
            expect(page.locator("#textRuleResults")).to_contain_text(
                "Sample 1: BLOCK"
            )
            expect(page.locator("#textRuleResults")).to_contain_text(
                "Sample 2: NO MATCH"
            )
            page.locator("#textRuleResults").scroll_into_view_if_needed()
            shot("local-rule")
            hold(6)
            page.locator("#textRuleReviewed").check()
            page.locator("#activateTextRule").click()
            expect(page.locator("#textRuleMessage")).to_contain_text(
                "No restart is needed"
            )
            mark("Reviewed policy activated. The same gateway keeps running.")
            hold(3)
            page.locator("#closeTextRule").click()
            nav("requests")
            with page.expect_response("**/api/models/complete") as response:
                page.locator("#invokeBtn").click()
            blocked = response.value.json()
            assert blocked["decision"] == "blocked"
            assert blocked["reason"] == "input_text_rule"
            assert not blocked["upstream_executed"]
            assert blocked["semantic_input_status"] == "not_run"
            expect(page.locator("#result")).to_contain_text("BLOCKED")
            results["after_local_rule"] = {
                key: blocked[key]
                for key in (
                    "decision",
                    "reason",
                    "upstream_executed",
                    "policy_version",
                    "latency_ms",
                )
            }
            mark(
                "Same 'Hello', now BLOCKED locally before model execution. No restart."
            )
            shot("blocked")
            hold(8)
            page.get_by_role("button", name="Inspect in Activity").click()
            expect(page.locator("#events")).to_contain_text("Not executed")
            mark(
                "The audit explains the decision, policy version and execution boundary."
            )
            shot("audit")
            hold(6)
            nav("policies")
            page.locator("#layaRuleBtn").click()
            mark(
                "3. Describe a semantic rule in plain language, with explicit expected outcomes."
            )
            page.locator("#layaRuleId").fill("demo-financial-guidance")
            page.locator("#layaRuleInstruction").fill(
                "Block personalized financial recommendations. General financial definitions are allowed."
            )
            page.locator("#layaRuleDirection").select_option("both")
            page.locator("#layaRuleTarget").select_option("all")
            page.locator("#layaRuleBlockSamples").fill(
                "Buy this stock immediately with all your savings."
            )
            page.locator("#layaRulePermitSamples").fill(
                "Define a stock as a financial instrument."
            )
            page.locator("#layaRuleDialog").evaluate(
                "dialog => dialog.scrollTop = 0"
            )
            page.locator("#layaRuleDialog").screenshot(
                path=str(assets / "demo-semantic-rule.png")
            )
            (assets / "policy-rule.png").write_bytes(
                (assets / "demo-semantic-rule.png").read_bytes()
            )
            page.locator("#layaRuleCallCount").scroll_into_view_if_needed()
            hold(6)
            mark(
                "Real Laya review: 8 scoped cases, active versus proposed policy. Waiting live."
            )
            with page.expect_response(
                "**/api/admin/semantic/review", timeout=150_000
            ) as response:
                page.locator("#layaRuleTest").click()
            review = response.value.json()
            assert review["tests_passed"] and review["review_id"]
            assert len(review["cases"]) == 8
            expect(page.locator("#layaRuleTestResult")).to_contain_text(
                "All reviewed expectations passed"
            )
            page.locator("#layaRuleResults").scroll_into_view_if_needed()
            mark(
                "All 8 reviewed cases pass. Input + output, models + tools. No business call during review."
            )
            shot("semantic-review")
            hold(8)
            page.locator("#layaRuleConfirmed").check()
            with page.expect_response(
                "**/api/admin/semantic/activate"
            ) as response:
                page.locator("#activateLayaRule").click()
            activation = response.value.json()
            assert activation["tests_saved"]
            results["semantic_review"] = {
                "cases": len(review["cases"]),
                "tests_passed": review["tests_passed"],
                "policy_version": activation["policy_version"],
                "tests_saved": True,
            }
            mark(
                "Explicit confirmation activates the tested policy and saves regression cases."
            )
            hold(4)
            page.locator("#closeLayaRule").click()
            nav("policies")
            shot("policies")
            hold(5)
            nav("overview")
            page.evaluate("refresh()")
            final = page.evaluate("latestStatus")
            assert final["runtime"]["instance_id"] == instance
            assert final["policy"]["version"] > initial["policy"]["version"]
            results["same_instance"] = True
            results["semantic_calls"] = (
                final["metrics"]["semantic_calls"]
                - initial["metrics"]["semantic_calls"]
            )
            mark(
                "Fast local enforcement. Reviewed semantic policies. Visible, exportable decisions."
            )
            shot("overview-final")
            hold(max(5, 90 - (time.monotonic() - origin)))
            duration = time.monotonic() - origin
            assert duration < 155, (
                "Demo exceeded target duration; inspect real timings before editing"
            )
            video = page.video
            context.close()
            raw = Path(video.path())
            browser.close()
        export_video(raw, target, captions, duration, trim)
    report = {
        "product_version": "1.0.7",
        "source": "public_pypi_isolated_gateway",
        "duration_seconds": round(duration, 2),
        "mocked_api_responses": False,
        "edits": "Credential connection trimmed; explanatory captions added. Action footage is continuous.",
        **results,
    }
    (target.parent / "demo-evidence.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    sys.stdout.write(json.dumps(report) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--agent-key", default="agent")
    parser.add_argument("--admin-key", default="admin")
    parser.add_argument("--model", default="qwen3:0.6b")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("presentation/output/fastfence-demo.mp4"),
    )
    parser.add_argument(
        "--assets", type=Path, default=Path("presentation/assets")
    )
    parser.add_argument(
        "--isolated-demo-confirmed", action="store_true", required=True
    )
    record(parser.parse_args())


if __name__ == "__main__":
    main()
