"""Capture actual protected document requests through the product UI."""

import json
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def capture(args, folder):
    credentials = json.loads(args.credentials.read_text())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(folder / "raw"),
            record_video_size={"width": 1600, "height": 900},
            accept_downloads=True,
        )
        started = time.monotonic()
        page = context.new_page()
        page.set_default_timeout(180000)
        page.add_init_script("""(() => {
          window.__ocrResponses = [];
          const actualFetch = window.fetch;
          window.fetch = async (...args) => {
            const response = await actualFetch(...args);
            if (String(args[0]).startsWith('/api/documents/markdown?')) {
              window.__ocrResponses.push({status: response.status, body: await response.clone().json()});
            }
            return response;
          };
        })();""")
        assert (
            context.request.get(args.url + "/openapi.json").json()["info"][
                "version"
            ]
            == "1.0.7"
        )
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
        assert initial["policy"]["privacy"]["input"] == "redact"
        origin = time.monotonic()
        trim = origin - started
        captions = []

        def mark(message):
            captions.append((time.monotonic() - origin, message))

        def hold(seconds):
            page.wait_for_timeout(seconds * 1000)

        def shot(name):
            page.screenshot(
                path=str(args.assets / ("demo-ocr-" + name + ".png"))
            )

        mark(
            "4. Documents: local OCR, protected Markdown, then a real model response."
        )
        page.locator('nav [data-nav="policies"]').click()
        page.locator("#policyBtn").click()
        expect(page.locator("#policyPrivacyInput")).to_have_value("redact")
        shot("privacy")
        hold(4)
        page.locator("#closePolicy").click()
        page.locator('nav [data-nav="documents"]').click()
        page.locator("#documentFile").set_input_files(args.document)
        page.locator("#documentMode").select_option("extract")
        mark(
            "Upload the actual two-page PDF. Local OCR extracts text; input privacy redacts matches."
        )
        shot("upload")
        hold(3)
        page.locator("#documentRun").click()
        for _ in range(900):
            if page.evaluate("window.__ocrResponses.length") >= 1:
                break
            page.wait_for_timeout(200)
        else:
            raise TimeoutError("Actual document extraction did not complete")
        observed = page.evaluate("window.__ocrResponses[0]")
        extracted = observed["body"]
        assert observed["status"] == 200, extracted.get("verdict", {}).get(
            "reason"
        )
        assert extracted["verdict"]["decision"] == "redacted"
        assert "pii_email" in extracted["verdict"]["findings"]
        assert extracted["markdown"].count("[REDACTED:pii_email]") == 2
        assert extracted["pages"] == 2
        assert extracted["ocr_elapsed_ms"] > 0
        assert extracted["markdown"]
        assert not extracted["verdict"]["upstream_executed"]
        for value in args.expected_redacted:
            assert value.casefold() not in extracted["markdown"].casefold()
        expect(page.locator("#documentMarkdown")).not_to_be_empty()
        with page.expect_download() as download:
            page.locator("#documentDownload").click()
        approved = args.output.parent / "demo-document-approved.md"
        download.value.save_as(approved)
        assert approved.read_text() == extracted["markdown"]
        mark(
            "Two pages become approved Markdown. Synthetic email values are removed before model use."
        )
        shot("markdown")
        hold(7)
        page.locator("#documentMode").select_option("complete")
        page.locator("#documentModel").fill(args.model)
        page.locator("#documentTokens").fill("128")
        mark(
            "Send protected Markdown to Qwen. The original PDF is not sent to the business model."
        )
        hold(3)
        page.locator("#documentRun").click()
        for _ in range(900):
            if page.evaluate("window.__ocrResponses.length") >= 2:
                break
            page.wait_for_timeout(200)
        else:
            raise TimeoutError("Actual document model request did not complete")
        observed = page.evaluate("window.__ocrResponses[1]")
        completed = observed["body"]
        assert observed["status"] == 200, completed.get("verdict", {}).get(
            "reason"
        )
        verdict = completed["verdict"]
        assert completed["pages"] == 2 and verdict["upstream_executed"]
        assert verdict["decision"] == "redacted"
        assert "pii_email" in verdict["findings"]
        assert completed["markdown"].count("[REDACTED:pii_email]") == 2
        assert verdict["semantic_input_status"] == "passed"
        assert verdict["semantic_output_status"] == "passed"
        assert verdict["output"]
        for value in args.expected_redacted:
            assert value.casefold() not in completed["markdown"].casefold()
            assert (
                value.casefold() not in json.dumps(verdict["output"]).casefold()
            )
        expect(page.locator("#documentVerdict")).to_contain_text(
            "The upstream was executed"
        )
        page.locator("#documentVerdict").scroll_into_view_if_needed()
        mark(
            "Real model output, with Laya input and output checks. No edited PDF is produced."
        )
        shot("model-response")
        hold(6)
        page.locator("#documentMarkdown").scroll_into_view_if_needed()
        hold(max(4, 45 - (time.monotonic() - origin)))
        duration = time.monotonic() - origin
        final = page.evaluate("latestStatus")
        assert (
            final["runtime"]["instance_id"] == initial["runtime"]["instance_id"]
        )
        video = page.video
        context.close()
        raw = Path(video.path())
        browser.close()
    report = {
        "product_version": "1.0.7",
        "source": "public_pypi_isolated_gateway",
        "actual_ocr": True,
        "mocked_api_responses": False,
        "pages": extracted["pages"],
        "extract_ocr_ms": extracted["ocr_elapsed_ms"],
        "complete_ocr_ms": completed["ocr_elapsed_ms"],
        "extract_decision": extracted["verdict"]["decision"],
        "extract_findings": extracted["verdict"]["findings"],
        "model_findings": verdict["findings"],
        "redaction_markers_in_each_markdown": 2,
        "extract_upstream_executed": extracted["verdict"]["upstream_executed"],
        "model_upstream_executed": verdict["upstream_executed"],
        "decision": verdict["decision"],
        "semantic_input_status": verdict["semantic_input_status"],
        "semantic_output_status": verdict["semantic_output_status"],
        "synthetic_sensitive_values_absent": True,
        "approved_markdown_is_exact_ui_download": True,
        "same_instance": True,
        "semantic_calls": final["metrics"]["semantic_calls"]
        - initial["metrics"]["semantic_calls"],
        "ui_duration_seconds": round(duration, 3),
    }
    return raw, captions, duration, trim, report
