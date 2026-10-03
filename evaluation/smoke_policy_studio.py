"""Isolated browser acceptance checks; optional actual Laya/Qwen authoring."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from playwright.sync_api import expect, sync_playwright

from fastfence.app.interfaces.cli.main import initialize


@contextmanager
def gateway():
    repo = Path.cwd()
    with TemporaryDirectory(prefix="fastfence-browser-") as directory:
        root = Path(directory)
        (root / "config").mkdir()
        shutil.copy(
            repo / "config/policy.offline.yaml", root / "config/policy.yaml"
        )
        shutil.copy(
            repo / "config/signatures.json", root / "config/signatures.json"
        )
        initialize(root / "state")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = {
            **os.environ,
            "FASTFENCE_ROOT": str(root),
            "FASTFENCE_STATE": str(root / "state"),
            "FASTFENCE_AUTHORING_ROOT": str(repo),
        }
        with (root / "gateway.log").open("w") as log:
            process = subprocess.Popen(
                [
                    "uv",
                    "run",
                    "uvicorn",
                    "fastfence.app.factory:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=repo,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            url = f"http://127.0.0.1:{port}"
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Isolated gateway did not start")
                    try:
                        if (
                            httpx.get(url + "/health", timeout=0.5).status_code
                            == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Isolated gateway startup timeout")
                yield (
                    url,
                    json.loads((root / "state/demo-tokens.json").read_text()),
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def connect(page, tokens):
    page.locator("#connectBtn").click()
    page.locator("#agentToken").fill(tokens["analyst-blue"])
    page.locator("#adminToken").fill(tokens["security-admin"])
    page.locator("#saveConnect").click()
    expect(page.locator("#connectDialog")).not_to_be_visible()
    expect(page.locator("#version")).to_have_text("Policy v1")


def fixture_authoring(page):
    """UI contract fixtures only, clearly separated from actual model evidence."""
    proposal = {
        "proposal_id": "fixture-proposal",
        "base_version": 1,
        "expires_at": "2099-01-01T00:00:00Z",
        "source": "UI_contract_fixture",
        "model": "explicit-test-fixture",
        "inference_ms": 0,
        "operations": [{"type": "test-fixture"}],
        "changes": [
            {
                "path": "<img src=x onerror=alert(1)>",
                "before": None,
                "after": "a",
            }
        ],
        "warnings": [],
    }
    page.route(
        "**/api/admin/policies/draft",
        lambda route: route.fulfill(json=proposal),
    )
    page.route(
        "**/api/admin/policies/preview",
        lambda route: route.fulfill(
            json={
                **proposal,
                "results": [
                    {
                        "index": 0,
                        "decision": "no_local_match",
                        "reason": "fixture",
                        "findings": [],
                        "safe_text": "Hello",
                    },
                    {
                        "index": 1,
                        "decision": "blocked",
                        "reason": "input_text_rule",
                        "findings": ["no-letter-a"],
                        "safe_text": None,
                    },
                ],
            }
        ),
    )


def studio_checks(page, live):
    if not live:
        fixture_authoring(page)
    page.locator("#policyStudioHero").click()
    page.locator('[data-policy-example="letters"]').click()
    expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    page.locator("#draftPolicy").click()
    expect(page.locator("#policyDraftSection")).to_be_visible(timeout=150_000)
    expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    assert page.locator("#policyDiff img").count() == 0
    page.locator("#previewPolicy").click()
    expect(page.locator("#policySampleResults")).to_contain_text("BLOCKED")
    expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    page.locator("#policyReviewed").check()
    expect(page.locator("#activatePolicyDraft")).to_be_enabled()
    page.locator("#policySamples").fill("Hello\nCat\nTiny")
    expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    page.locator("#previewPolicy").click()
    expect(page.locator("#policySampleResults")).to_contain_text("BLOCKED")
    page.locator("#policyReviewed").check()
    if live:
        page.locator("#activatePolicyDraft").click()
        expect(page.locator("#policyStudioMessage")).to_contain_text(
            "is active"
        )
        expect(page.locator("#version")).to_have_text("Policy v2")
    else:
        page.locator("#policyInstruction").fill("Changed instruction")
        expect(page.locator("#policyDraftSection")).not_to_be_visible()
        expect(page.locator("#activatePolicyDraft")).to_be_disabled()
    page.locator("#closePolicyStudio").click()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=Path("state/policy-studio-qa.json")
    )
    parser.add_argument("--screenshots", type=Path, default=Path("state/ui-qa"))
    args = parser.parse_args()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    with gateway() as (url, tokens), sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        failures = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.goto(url)
        connect(page, tokens)
        studio_checks(page, args.live)
        page.locator("#playgroundMode").select_option("model")
        expect(page.locator("#modelPlayground")).to_be_visible()
        expect(page.locator("#toolPlayground")).not_to_be_visible()
        if args.live:
            page.locator("#completionPrompt").fill("Cat")
            page.locator("#invokeBtn").click()
            expect(page.locator("#result")).to_contain_text("input_text_rule")
            expect(page.locator("#result")).to_contain_text(
                "upstream not executed"
            )
            expect(page.locator("#events")).to_contain_text("input_text_rule")
            # Actual MCP transport and one bounded real Qwen completion.
            result = httpx.post(
                url + "/mcp/",
                headers={
                    "Authorization": "Bearer " + tokens["analyst-blue"],
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "complete",
                        "arguments": {
                            "model": "qwen3:0.6b",
                            "prompt": "Hi",
                            "max_output_tokens": 1,
                        },
                    },
                },
                timeout=40,
            )
            result.raise_for_status()
            verdict = result.json()["result"]["structuredContent"]
            assert (
                verdict["decision"] == "allowed"
                and verdict["upstream_executed"]
            )
            assert verdict["output"]["text"].strip()
            page.locator("#refreshBtn").click()
            expect(page.locator("#events")).to_contain_text("controls_passed")
        page.screenshot(
            path=str(args.screenshots / "dashboard-desktop.png"), full_page=True
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        page.screenshot(
            path=str(args.screenshots / "dashboard-mobile.png"), full_page=True
        )
        assert not failures, "Browser JavaScript errors occurred"
        browser.close()
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "actual_laya_and_gateway"
        if args.live
        else "UI_contract_fixtures_only",
        "checks": [
            "identity_connection",
            "draft_review",
            "preview_before_activation",
            "changed_examples_invalidate_preview",
            "safe_diff_rendering",
            "responsive_layout",
            "model_playground",
        ],
        "all_passed": True,
    }
    if args.live:
        report["checks"] += [
            "actual_laya_draft",
            "exact_proposal_activation",
            "input_block_before_upstream",
            "audit_visible",
            "actual_one_token_qwen_completion_via_mcp",
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
