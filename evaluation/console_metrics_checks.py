"""Browser assertions for scoped dashboard metrics using synthetic responses."""

from playwright.sync_api import expect


def metric_checks(page, fixture, screenshots=None):
    expect(page.locator("#queueActive")).to_have_text("—")
    fixture.status["request_queue"] = {
        "active": 8,
        "waiting": 57,
        "max_active": 8,
        "max_waiting": 1024,
        "wait_timeout_ms": 120000,
    }
    fixture.status["metrics"].update(
        requests=250,
        allowed=243,
        blocked=4,
        redacted=1,
        errors=2,
        semantic_requests=50,
        local_only_requests=200,
        semantic_calls=100,
        throughput_rps=12.345,
        throughput_window_seconds=60,
        p95_latency_ms=123,
        latency_sample_size=250,
    )
    base = {
        "time": "2026-10-04T00:00:00Z",
        "subject": "synthetic-agent",
        "tenant": "synthetic",
        "target": "synthetic-tool",
        "decision": "allowed",
        "reason": "controls_passed",
        "policy_version": 1,
        "latency_ms": 401,
        "queue_wait_ms": 400,
        "event_kind": "invocation",
    }
    rows = [{**base, "request_id": f"fixture-{i}"} for i in range(201)]
    for index in (0, 1):
        rows[index].update(decision="blocked", reason="attack_signature")
    rows[2].update(decision="blocked", reason="semantic_input_risk")
    rows[3].update(decision="blocked", reason='<img src=x onerror="alert(1)">')
    rows[4].update(
        decision="blocked",
        reason="management-excluded",
        event_kind="management",
    )
    rows[5].update(decision="error", reason="error-not-denial")
    rows[200].update(decision="blocked", reason="outside-window")
    fixture.status["audit"] = rows
    page.locator('nav [data-nav="activity"]').click()
    page.locator("#refreshBtn").click()
    page.locator('nav [data-nav="overview"]').click()
    for name, expected in {
        "requests": "250",
        "allowed": "243",
        "blocked": "4",
        "redacted": "1",
        "errors": "2",
        "localPathShare": "80.0%",
        "semanticPathShare": "20.0%",
        "throughput": "12.35",
        "latency": "123 ms",
        "queueActive": "8 / 8",
        "queueWaiting": "57 / 1024",
        "queueTimeout": "120 s",
    }.items():
        expect(page.locator("#" + name)).to_have_text(expected)
    expect(page.locator("#throughputScope")).to_contain_text("Last 60 seconds")
    expect(page.locator("#latencyScope")).to_have_text(
        "Last 250 decisions · integer ms · includes queue wait and upstream, excludes gateway transport"
    )
    expect(page.locator("#threatScope")).to_contain_text(
        "199 invocation events"
    )
    denials = page.locator("#topDenialReasons")
    expect(denials.locator(".control").first).to_have_text(
        "Known attack signature2"
    )
    for excluded in (
        "management-excluded",
        "error-not-denial",
        "outside-window",
    ):
        expect(denials).not_to_contain_text(excluded)
    expect(denials).to_contain_text('<img src=x onerror="alert(1)">')
    assert denials.locator("img").count() == 0
    expect(denials.locator("[title=attack_signature]")).to_have_text(
        "Known attack signature"
    )
    expect(denials).to_contain_text("Semantic policy violation in input")
    expect(page.locator("#queueScope")).to_contain_text("FIFO admission")
    page.locator('nav [data-nav="activity"]').click()
    page.locator("#events button").first.click()
    expect(page.locator("#audit-detail-0")).to_contain_text(
        "Queue wait: 400 ms (included in total latency)"
    )
    page.locator('nav [data-nav="requests"]').click()
    for reason, message in {
        "request_queue_full": "Request queue full; request was not admitted",
        "request_queue_timeout": "Request queue wait expired; request was not admitted",
        "request_queue_closed": "Request queue closed; request was not admitted",
    }.items():
        page.evaluate(
            "v => renderVerdict(v)",
            {
                **base,
                "decision": "error",
                "reason": reason,
                "feed_version": 1,
                "semantic_provider": "disabled",
                "semantic_score": None,
                "upstream_executed": False,
            },
        )
        expect(page.locator("#result")).to_contain_text(message)
        expect(page.locator("#result")).to_contain_text("Queue wait: 400 ms")
        expect(page.locator("#result")).to_contain_text("401 ms total")
        expect(page.locator("#result")).to_contain_text(
            "upstream was not executed"
        )
    page.locator('nav [data-nav="overview"]').click()
    if screenshots:
        page.screenshot(
            path=str(screenshots / "metrics-desktop.png"), full_page=True
        )
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if screenshots:
        page.screenshot(
            path=str(screenshots / "metrics-mobile.png"), full_page=True
        )
    del fixture.status["request_queue"]
    page.evaluate("refresh()")
    expect(page.locator("#queueWaiting")).to_have_text("—")
    expect(page.locator("#queueScope")).to_contain_text("unavailable")
    fixture.status["request_queue"] = {"active": "<img src=x onerror=alert(1)>"}
    page.evaluate("refresh()")
    expect(page.locator("#queueActive")).to_have_text("—")
    assert page.locator("#requestQueuePanel img").count() == 0
    fixture.status["request_queue"] = {
        "active": 0,
        "waiting": 0,
        "max_active": 8,
        "max_waiting": 1024,
        "wait_timeout_ms": 120000,
    }
    page.evaluate("refresh()")
    expect(page.locator("#queueActive")).to_have_text("0 / 8")
    expect(page.locator("#queueWaiting")).to_have_text("0 / 1024")
    fixture.status_error = True
    page.locator('nav [data-nav="activity"]').click()
    page.locator("#refreshBtn").click()
    expect(page.locator("#globalMessage")).to_contain_text("may be stale")
    expect(page.locator("#allowed")).to_have_text("243")
    expect(page.locator("#queueWaiting")).to_have_text("0 / 1024")
    fixture.status_error = False
    page.locator('nav [data-nav="connection"]').click()
    page.locator("#disconnectBtn").click()
    for name in (
        "allowed",
        "errors",
        "throughput",
        "localPathShare",
        "semanticPathShare",
        "latency",
        "queueActive",
        "queueWaiting",
        "queueTimeout",
    ):
        expect(page.locator("#" + name)).to_have_text("—")
    expect(denials).not_to_contain_text("Known attack signature")
    expect(page.locator("#latencyScope")).not_to_contain_text("250")
    page.set_viewport_size({"width": 1440, "height": 1000})
