"""An operator probe must require the active snapshot, not merely a saved file."""

import copy
import json

import pytest

from scripts import smoke_uv_tool


@pytest.mark.parametrize("version", ["latest", "../1.0.0", "v1.0.0", "1.0"])
def test_uv_probe_rejects_nonexact_release_before_subprocess(
    monkeypatch, version
):
    monkeypatch.setattr(
        smoke_uv_tool.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("must not execute"),
    )
    with pytest.raises(ValueError, match="exact"):
        smoke_uv_tool.smoke(version)


def test_live_file_probe_preserves_other_settings_and_waits_for_activation(
    tmp_path,
):
    original = {
        "version": 7,
        "semantic": {"provider": "laya"},
        "budgets": {"analyst": {"calls": 20}},
    }
    current = copy.deepcopy(original)
    current["version"] = 8
    current["budgets"]["analyst"]["calls"] = 3
    observations = iter([{"policy": original}, {"policy": current}])
    (tmp_path / "config").mkdir()
    version = smoke_uv_tool.activate_file(
        tmp_path,
        lambda: next(observations),
        lambda policy: policy["budgets"]["analyst"].update(calls=3),
    )
    assert version == 8
    assert json.loads((tmp_path / "config/policy.yaml").read_text()) == current
    assert not (tmp_path / "config/policy.pending").exists()


def test_same_version_wrong_snapshot_does_not_pass_operator_probe(tmp_path):
    (tmp_path / "config").mkdir()
    observations = iter(
        [
            {"policy": {"version": 1, "setting": "before"}},
            {"policy": {"version": 2, "setting": "wrong"}},
        ]
    )
    with pytest.raises(AssertionError):
        smoke_uv_tool.activate_file(
            tmp_path,
            lambda: next(observations),
            lambda policy: policy.update(setting="after"),
        )
