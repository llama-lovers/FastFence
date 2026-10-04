import pytest
from pydantic import ValidationError

from fastfence.modules.control.application.facade import build_runtime
from fastfence.shared.request_size import RequestBytes, request_size
from fastfence.shared.settings.app_settings import AppSettings


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_concurrency", 0),
        ("request_concurrency", 129),
        ("request_queue_size", -1),
        ("request_queue_size", 4097),
        ("request_queue_timeout_seconds", 0),
        ("request_queue_timeout_seconds", 3601),
        ("request_queue_max_bytes", 0),
        ("request_queue_max_bytes", 268435457),
        ("request_queue_per_identity", 0),
        ("request_queue_per_identity", 1025),
    ],
)
def test_invalid_queue_limits(field, value):
    with pytest.raises(ValidationError):
        AppSettings(**{field: value})


async def test_startup_settings_and_runtime_snapshot(project, monkeypatch):
    monkeypatch.setenv("FASTFENCE_REQUEST_CONCURRENCY", "2")
    monkeypatch.setenv("FASTFENCE_REQUEST_QUEUE_SIZE", "17")
    monkeypatch.setenv("FASTFENCE_REQUEST_QUEUE_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("FASTFENCE_REQUEST_QUEUE_MAX_BYTES", "10000")
    monkeypatch.setenv("FASTFENCE_REQUEST_QUEUE_PER_IDENTITY", "5")
    runtime = build_runtime(AppSettings(root=project))
    try:
        assert runtime.status()["request_queue"] == {
            "active": 0,
            "waiting": 0,
            "max_active": 2,
            "max_waiting": 17,
            "wait_timeout_ms": 300000,
            "waiting_bytes": 0,
            "max_waiting_bytes": 10000,
            "per_identity": 5,
        }
    finally:
        await runtime.aclose()


def test_body_counter_survives_mounted_scope_copy():
    counter = RequestBytes()
    scope = {"fastfence.request_bytes": counter}
    mounted = dict(scope)
    counter.received += 1024
    assert request_size(mounted) == 1024
    assert (
        request_size({}) == request_size({"fastfence.request_bytes": -1}) == 0
    )
