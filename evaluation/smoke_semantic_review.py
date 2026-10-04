"""Real Chromium -> local HTTP app; only semantic inference is a declared fixture."""

import argparse
import contextlib
import io
import json
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

from examples.business_tools.credentials import initialize
from fastfence.app.factory import create_app
from fastfence.modules.control.domain.models import Assessment
from fastfence.shared.settings.app_settings import AppSettings


def run(screenshots=None):
    calls, requests, errors = [], [], []
    with tempfile.TemporaryDirectory(
        prefix="fastfence-semantic-browser-"
    ) as directory:
        root = Path(directory)
        (root / "config").mkdir()
        for source, name in [
            ("examples/business_tools/policy.yaml", "policy.yaml"),
            ("config/signatures.json", "signatures.json"),
        ]:
            shutil.copyfile(source, root / "config" / name)
        with contextlib.redirect_stdout(io.StringIO()):
            initialize(root / "state")
        tokens = json.loads((root / "state/demo-tokens.json").read_text())
        app = create_app(
            AppSettings(root=root, state=root / "state", _env_file=None)
        )

        async def assess(text, config):
            calls.append((text, [rule.id for rule in config.rules]))
            return Assessment(score=1 if text == "forbidden" else 0, tokens=10)

        async def forbidden(*args, **kwargs):
            raise AssertionError(
                "Management review must not execute a business model/tool"
            )

        app.state.engine.scanner.assess = assess
        app.state.engine.models.complete = forbidden
        app.state.engine.tools.call = forbidden
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        server = uvicorn.Server(
            uvicorn.Config(app, log_level="error", access_log=False)
        )
        worker = threading.Thread(
            target=server.run, kwargs={"sockets": [listener]}, daemon=True
        )
        worker.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not worker.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("Isolated browser app did not start")
                time.sleep(0.02)
            url = f"http://127.0.0.1:{listener.getsockname()[1]}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000}
                )
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "request",
                    lambda request: requests.append(
                        (request.method, request.url)
                    ),
                )
                page.goto(url)
                page.locator("#connectBtn").click()
                page.locator("#agentToken").fill(tokens["analyst-blue"])
                page.locator("#adminToken").fill(tokens["security-admin"])
                page.locator("#saveConnect").click()
                expect(page.locator("#connectDialog")).not_to_be_visible()
                page.locator('nav [data-nav="policies"]').click()
                page.locator("#layaRuleBtn").click()
                page.locator("#layaRuleId").fill("fixture-topics")
                page.locator("#layaRuleInstruction").fill(
                    "Block forbidden; permit Hello."
                )
                page.locator("#layaRuleBlockSamples").fill("forbidden")
                page.locator("#layaRulePermitSamples").fill("Hello")
                page.locator("#layaRuleTest").click()
                expect(page.locator("#layaRuleTestResult")).to_contain_text(
                    "All reviewed expectations passed"
                )
                expect(page.locator("#layaRuleResults tr")).to_have_count(8)
                assert (
                    len(calls) == 8
                )  # Active policy's semantic provider is disabled.
                assert app.state.runtime.snapshot().policy.version == 1
                page.locator("#layaRuleConfirmed").check()
                page.locator("#activateLayaRule").click()
                expect(page.locator("#layaRuleMessage")).to_contain_text(
                    "Policy v2 is active"
                )
                expect(page.locator("#layaRuleMessage")).to_contain_text(
                    "saved"
                )
                assert app.state.runtime.snapshot().policy.version == 2
                assert not any(method == "PUT" for method, _ in requests)
                page.locator("#closeLayaRule").click()
                card = page.locator("#policyInventory .rule-card").filter(
                    has_text="fixture-topics"
                )
                card.get_by_role("button", name="Edit rule", exact=True).click()
                expect(page.locator("#layaRuleSavedCases")).to_contain_text(
                    "Saved expectations loaded with their exact scopes"
                )
                assert page.evaluate("semanticCases().length") == 8
                expect(page.locator("#layaRuleNewCases")).not_to_be_visible()
                page.locator("#layaRuleTest").click()
                expect(page.locator("#layaRuleResults tr")).to_have_count(8)
                expect(page.locator("#layaRuleTestResult")).to_contain_text(
                    "All reviewed expectations passed"
                )
                assert (
                    len(calls) == 24
                )  # Both versions have actual assessment fixtures.
                if screenshots:
                    screenshots.mkdir(parents=True, exist_ok=True)
                    page.screenshot(
                        path=str(
                            screenshots
                            / "semantic-review-real-http-desktop.png"
                        ),
                        full_page=True,
                    )
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    page.screenshot(
                        path=str(
                            screenshots / "semantic-review-real-http-mobile.png"
                        ),
                        full_page=True,
                    )
                    page.set_viewport_size({"width": 1440, "height": 1000})
                page.locator("#closeLayaRule").click()
                page.locator("#replaySemanticTestsBtn").click()
                expect(page.locator("#semanticReplayMessage")).to_contain_text(
                    "8 saved scoped cases"
                )
                page.locator("#runSemanticReplay").click()
                expect(page.locator("#semanticReplayMessage")).to_contain_text(
                    "All evaluated expectations passed"
                )
                assert len(calls) == 32
                assert any(
                    path.endswith("/api/admin/semantic/tests/replay")
                    for _, path in requests
                )
                assert app.state.runtime.snapshot().policy.version == 2
                assert (
                    page.evaluate("localStorage.length + sessionStorage.length")
                    == 0
                )
                assert not errors, errors
                browser.close()
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            listener.close()
            if worker.is_alive():
                raise RuntimeError("Isolated browser app did not stop")
        return {
            "all_passed": True,
            "mode": "real_chromium_real_http_app_fixture_scanner",
            "actual_model_calls": 0,
            "fixture_assessments": len(calls),
            "checks": [
                "eight_real_scopes_reviewed",
                "exact_receipt_activation",
                "no_generic_policy_put",
                "saved_scope_preservation",
                "before_after_reassessment",
                "actual_replay_route",
                "replay_never_activates",
                "no_client_storage",
                "desktop_mobile_rendering",
            ],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    result = run(args.screenshots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
