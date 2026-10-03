"""OCR uses the same atomic reservation and policy snapshot as text controls."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from fastfence.modules.control.contracts.dto import Identity
from fastfence.modules.ocr.application.facade import OCRRuntime
from fastfence.shared.ocr import (
    OCRBlock,
    OCRDocument,
    OCRError,
    OCRLimits,
    OCRPage,
)
from fastfence.workflows.document_markdown import DocumentMarkdownWorkflow
from tests.fixtures.policy import configure_policy

IDENTITY = Identity(subject="ocr-reader", tenant="test", roles=["analyst"])


def document(text="Approved invoice"):
    return OCRDocument(
        pages=[
            OCRPage(
                number=1,
                width=100,
                height=100,
                blocks=[OCRBlock(text=text, confidence=1, x=0, y=0)],
            )
        ],
        elapsed_ms=1,
    )


@pytest.fixture
def admission(app):
    provider = Mock(extract=AsyncMock(return_value=document()))
    workflow = DocumentMarkdownWorkflow(
        OCRRuntime(provider, OCRLimits(timeout_seconds=1)), app.state.runtime
    )
    return workflow, provider, app.state.engine


async def run(workflow, **kwargs):
    return await workflow.run(
        b"synthetic-image", "image/png", IDENTITY, **kwargs
    )


@pytest.mark.parametrize("mode", [False, True])
@pytest.mark.parametrize(
    "restriction,reason",
    [
        ("unknown", "target_not_allowlisted"),
        ("role", "role_not_allowed"),
        ("tokens", "budget_tokens"),
        ("compute_ms", "budget_compute_ms"),
        ("cost_microusd", "budget_cost_microusd"),
    ],
)
async def test_denied_document_never_starts_ocr_or_model(
    admission, mode, restriction, reason
):
    workflow, provider, engine = admission
    model = "unlisted" if restriction == "unknown" else "qwen3:0.6b"

    def restrict(policy):
        if restriction == "role":
            policy["models"][model]["roles"] = ["operator"]
        elif restriction in {"tokens", "compute_ms", "cost_microusd"}:
            policy["budgets"]["analyst"][restriction] = 1
            if restriction == "cost_microusd":
                policy["models"][model]["cost_microusd"] = 2

    configure_policy(engine, restrict)
    result = await run(workflow, model=model, complete=mode)
    assert result.verdict.reason == reason
    assert result.markdown is None and result.pages == 0
    assert result.provider == "not_run"
    assert not result.verdict.upstream_executed
    provider.extract.assert_not_awaited()
    assert not engine.ledger._reservations


async def test_exhausted_calls_block_before_ocr_without_double_charge(
    admission,
):
    workflow, provider, engine = admission
    configure_policy(
        engine, lambda policy: policy["budgets"]["analyst"].update(calls=1)
    )
    first = await run(workflow)
    second = await run(workflow)
    assert first.verdict.decision == "allowed"
    assert second.verdict.reason == "budget_calls"
    provider.extract.assert_awaited_once()
    assert engine.ledger.budgets()[0]["calls"] == 1
    assert not engine.ledger._reservations


async def test_concurrent_ocr_holds_atomic_slot_and_cancel_refunds_unused_resources(
    admission,
):
    workflow, provider, engine = admission
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def pending(*_args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    provider.extract.side_effect = pending
    configure_policy(
        engine, lambda policy: policy["budgets"]["analyst"].update(concurrent=1)
    )
    first = asyncio.create_task(run(workflow))
    await started.wait()
    second = await run(workflow)
    assert second.verdict.reason == "budget_inflight"
    provider.extract.assert_awaited_once()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert stopped.is_set() and not engine.ledger._reservations
    usage = engine.ledger.budgets()[0]
    assert (
        usage["calls"] == 1
        and usage["tokens"] == 0
        and usage["cost_microusd"] == 0
    )
    assert usage["compute_ms"] >= 1
    provider.extract.side_effect = None
    assert (await run(workflow)).verdict.decision == "allowed"


async def test_ocr_error_settles_and_preserves_static_provider_error(admission):
    workflow, provider, engine = admission
    provider.extract.side_effect = OCRError("ocr_page_failed")
    with pytest.raises(OCRError, match="ocr_page_failed"):
        await run(workflow)
    usage = engine.ledger.budgets()[0]
    assert usage["tokens"] == 0 and usage["cost_microusd"] == 0
    assert usage["calls"] == 1 and usage["compute_ms"] >= 1
    assert not engine.ledger._reservations


async def test_preparation_timeout_cancels_work_and_refunds_unused_tokens(app):
    stopped = asyncio.Event()

    async def source():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    verdict, safe = await app.state.runtime.process_document(
        IDENTITY, source, timeout_ms=10
    )
    assert verdict.reason == "document_preparation_timeout" and safe is None
    assert stopped.is_set() and not app.state.engine.ledger._reservations
    usage = app.state.engine.ledger.budgets()[0]
    assert usage["tokens"] == 0 and usage["compute_ms"] >= 10


async def test_measured_ocr_time_and_snapshot_are_retained_through_inspection(
    admission,
):
    workflow, provider, engine = admission
    version = engine.policies.snapshot().policy.version

    async def extract(*_args):
        await asyncio.sleep(0.02)
        # Reload during OCR must not switch the admitted request's policy.
        configure_policy(engine, lambda policy: policy.update(models={}))
        return document()

    provider.extract.side_effect = extract
    result = await run(workflow)
    assert result.verdict.decision == "allowed"
    assert result.verdict.policy_version == version
    assert result.verdict.latency_ms >= 20
    assert engine.ledger.budgets()[0]["compute_ms"] >= 20
    assert engine.ledger.budgets()[0]["calls"] == 1
