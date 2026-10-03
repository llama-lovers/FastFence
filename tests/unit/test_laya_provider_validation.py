"""The response guard must run before provider wrappers normalize completion state."""

from types import SimpleNamespace

import pytest

from integrations.laya.semantic_response import (
    guard_provider_completion,
    validate_provider_response,
)


def response(**choice_overrides):
    choice = SimpleNamespace(
        **{
            "finish_reason": "stop",
            "message": SimpleNamespace(content='{"severity":"benign"}'),
            **choice_overrides,
        }
    )
    return SimpleNamespace(choices=[choice])


@pytest.mark.parametrize(
    "finish_reason", [None, "length", "tool_calls", "content_filter", ""]
)
def test_only_explicit_stop_is_accepted(finish_reason):
    with pytest.raises(ValueError, match="explicitly stop"):
        validate_provider_response(response(finish_reason=finish_reason))


def test_missing_stop_is_rejected_before_it_can_be_defaulted():
    payload = response()
    del payload.choices[0].finish_reason
    with pytest.raises(ValueError, match="explicitly stop"):
        validate_provider_response(payload)


@pytest.mark.parametrize(
    "override",
    [
        {"tool_calls": [{"id": "call-1"}]},
        {"function_call": {"name": "tool"}},
        {"refusal": "refused"},
        {"content": '<think>private</think>{"severity":"benign"}'},
        {"content": '{"severity":"malicious","severity":"benign"}'},
        {"content": '{"severity":"benign","extra":true}'},
        {"content": None, "reasoning_content": '{"severity":"benign"}'},
    ],
)
def test_raw_content_and_modes_cannot_be_salvaged(override):
    payload = response(
        message=SimpleNamespace(
            **{
                "content": '{"severity":"benign"}',
                **override,
            }
        )
    )
    with pytest.raises(ValueError):
        validate_provider_response(payload)


@pytest.mark.parametrize(
    "choices", [[], None, [SimpleNamespace(), SimpleNamespace()]]
)
def test_missing_or_multiple_choices_fail_closed(choices):
    with pytest.raises(ValueError, match="choices"):
        validate_provider_response(SimpleNamespace(choices=choices))


async def test_guard_keeps_actual_transport_result_and_arguments():
    calls = []
    original = ({"header": "value"}, response())

    async def transport(*args, **kwargs):
        calls.append((args, kwargs))
        return original

    guarded = guard_provider_completion(transport)
    result = await guarded("original-client", request="original-request")
    assert result is original
    assert calls == [(("original-client",), {"request": "original-request"})]


async def test_worker_environment_blocks_dotenv_reload_and_inherited_values(
    tmp_path, monkeypatch
):
    from fastfence.modules.control.persistence import laya_semantic

    for name in [
        "state/laya/venv/bin/python",
        "integrations/laya/semantic_worker.py",
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (tmp_path / "state/laya/upstream").mkdir()
    monkeypatch.setenv("LITELLM_MODE", "DEV")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "0")
    monkeypatch.setenv(
        "FASTFENCE_ANONYMIZATION_KEYS_JSON", "private-env-marker"
    )
    seen = []

    async def spawn(*args, **kwargs):
        seen.append(kwargs["env"])
        return SimpleNamespace()

    monkeypatch.setattr(laya_semantic.asyncio, "create_subprocess_exec", spawn)
    adapter = laya_semantic.LayaSemantic(tmp_path, "http://127.0.0.1:11434")
    await adapter._start()
    assert seen[0]["LITELLM_MODE"] == "PRODUCTION"
    assert seen[0]["PYTHON_DOTENV_DISABLED"] == "1"
    assert "FASTFENCE_ANONYMIZATION_KEYS_JSON" not in seen[0]
    assert "private-env-marker" not in seen[0].values()
