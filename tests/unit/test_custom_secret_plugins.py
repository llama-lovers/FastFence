"""Trusted extension loading and request-time redaction fail safely."""

import builtins
import io
import json
from pathlib import Path

import pytest
from detect_secrets.plugins.base import BasePlugin

from fastfence.modules.control.application.facade import build_runtime
from fastfence.modules.control.application.services.inspection import (
    inspect_privacy,
)
from fastfence.modules.control.domain.exceptions import RejectedError
from fastfence.modules.control.persistence.secrets import MARKER, OfflineSecrets
from fastfence.shared.settings.app_settings import AppSettings
from tests.fixtures.policy import configure_policy
from tests.fixtures.secrets import GITHUB_FIXTURE

EXAMPLE = Path("examples/docs/custom_detector.py")


def plugin(tmp_path, content):
    path = tmp_path / "detector.py"
    path.write_text(content)
    return path


def custom_detector(tmp_path):
    return OfflineSecrets((plugin(tmp_path, EXAMPLE.read_text()),))


def test_custom_regex_literal_and_base_plugin_keep_builtins(tmp_path, capsys):
    detector = custom_detector(tmp_path)
    original = {
        "ACME-DEMO-1234": [
            "prefix PROJECT ORCHID INTERNAL suffix",
            {"nested": "EXAMPLE INTERNAL ONLY"},
        ],
        "builtin": GITHUB_FIXTURE,
    }
    safe, findings = detector.redact(original)
    assert safe[MARKER] == [f"prefix {MARKER} suffix", {"nested": MARKER}]
    assert GITHUB_FIXTURE not in json.dumps(safe)
    assert "detect_secrets_CompanyCodeDetector" in findings
    assert "detect_secrets_InternalPhraseDetector" in findings
    assert original["builtin"] == GITHUB_FIXTURE
    assert capsys.readouterr() == ("", "")


def test_loaded_plugins_do_not_read_files_or_verify(tmp_path, monkeypatch):
    path = plugin(tmp_path, EXAMPLE.read_text())
    first = OfflineSecrets((path,))
    path.write_text("raise RuntimeError('changed after startup')")

    second = OfflineSecrets((path,))

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected request-time I/O")

    with monkeypatch.context() as guard:
        for owner, name in [(builtins, "open"), (io, "open"), (Path, "open")]:
            guard.setattr(owner, name, forbidden)
        guard.setattr(BasePlugin, "verify", forbidden)
        assert second.redact("ACME-DEMO-1234") == first.redact("ACME-DEMO-1234")


@pytest.mark.parametrize(
    "content",
    [
        "broken python !",
        "raise RuntimeError('PRIVATE SOURCE DETAIL')",
        "from detect_secrets.plugins.base import BasePlugin\nclass Broken(BasePlugin):\n secret_type='x'\n analyze_string='PRIVATE SOURCE DETAIL'",
        "x = 1",
        "from detect_secrets.plugins.aws import AWSKeyDetector",
        "from detect_secrets.plugins.base import BasePlugin\nclass Broken(BasePlugin): pass",
        "from detect_secrets.plugins.base import RegexBasedDetector\nclass Broken(RegexBasedDetector):\n secret_type='x'\n denylist=('plain string',)",
        "import re\nfrom detect_secrets.plugins.base import RegexBasedDetector\nclass Broken(RegexBasedDetector):\n secret_type='x'\n denylist=(re.compile('.*'),)",
        "from detect_secrets.plugins.base import BasePlugin\nclass AWSKeyDetector(BasePlugin):\n secret_type='x'\n def analyze_string(self, string): return iter(())",
    ],
)
def test_invalid_plugins_have_static_startup_errors(tmp_path, content):
    with pytest.raises(ValueError) as caught:
        OfflineSecrets((plugin(tmp_path, content),))
    assert str(caught.value).startswith("Custom secret detector configuration")
    assert "PRIVATE SOURCE DETAIL" not in str(caught.value)
    assert str(tmp_path) not in str(caught.value)


def test_source_size_missing_file_and_file_count_are_bounded(tmp_path):
    with pytest.raises(ValueError):
        OfflineSecrets((tmp_path / "missing.py",))
    with pytest.raises(ValueError):
        OfflineSecrets((plugin(tmp_path, "#" * 1025),), 1024)
    with pytest.raises(ValueError):
        OfflineSecrets(tuple(tmp_path / f"{i}.py" for i in range(9)))


def test_environment_paths_are_explicit_and_relative_to_root(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FASTFENCE_SECRET_PLUGIN_FILES", '["custom.py"]')
    settings = AppSettings(root=tmp_path)
    assert settings.secret_plugin_files == [tmp_path / "custom.py"]
    monkeypatch.setenv("FASTFENCE_SECRET_PLUGIN_FILES", '["x.py", "x.py"]')
    with pytest.raises(ValueError):
        AppSettings(root=tmp_path)


def test_missing_plugin_stops_runtime_construction(project):
    with pytest.raises(ValueError, match="Custom secret detector"):
        build_runtime(
            AppSettings(root=project, secret_plugin_files=["missing.py"])
        )


@pytest.mark.parametrize("direction", ["input", "output"])
@pytest.mark.parametrize("action", ["block", "redact"])
def test_custom_findings_obey_both_privacy_directions(
    app, tmp_path, direction, action
):
    detector = custom_detector(tmp_path)
    configure_policy(
        app.state.engine,
        lambda data: data["privacy"].update({direction: action}),
    )
    snapshot = app.state.engine.policies.snapshot()
    if action == "block":
        with pytest.raises(RejectedError) as caught:
            inspect_privacy(
                {"nested": ["ACME-DEMO-1234"]}, snapshot, direction, detector
            )
        assert caught.value.reason == f"{direction}_sensitive_data"
    else:
        safe, findings = inspect_privacy(
            {"nested": ["ACME-DEMO-1234"]}, snapshot, direction, detector
        )
        assert safe == {"nested": [MARKER]}
        assert findings == ["detect_secrets_CompanyCodeDetector"]


@pytest.mark.parametrize(
    "body",
    [
        "raise RuntimeError(string)",
        "yield 12",
        "yield ''",
        "yield 'not present'",
        "yield from ('x' for _ in range(4097))",
    ],
)
def test_runtime_failure_and_invalid_results_fail_closed(
    app, tmp_path, body, capsys
):
    source = (
        "from detect_secrets.plugins.base import BasePlugin\nclass Broken(BasePlugin):\n secret_type='x'\n def analyze_string(self, string):\n  "
        + body
    )
    detector = OfflineSecrets((plugin(tmp_path, source),))
    with pytest.raises(RejectedError) as caught:
        inspect_privacy(
            "private x", app.state.engine.policies.snapshot(), "input", detector
        )
    assert caught.value.reason == "input_secret_detector_unavailable"
    assert "private x" not in str(caught.value)
    assert capsys.readouterr() == ("", "")


def test_runtime_loads_plugins_from_trusted_settings(project):
    path = plugin(project, EXAMPLE.read_text())
    runtime = build_runtime(
        AppSettings(root=project, secret_plugin_files=[path])
    )
    try:
        safe, findings = runtime.engine.secrets.redact("ACME-DEMO-1234")
        assert safe == MARKER
        assert findings == ["detect_secrets_CompanyCodeDetector"]
    finally:
        runtime.close()


async def test_full_gateway_blocks_input_and_redacts_output_without_raw_audit(
    app, tokens, tmp_path, monkeypatch
):
    from fastfence.modules.control.domain.models import ToolCall

    engine = app.state.engine
    engine.secrets = custom_detector(tmp_path)
    identity = app.state.identities.authenticate(tokens["analyst-blue"])
    attempts = []

    async def upstream(*args):
        attempts.append(args)
        return {"nested": ["PROJECT ORCHID INTERNAL"]}

    monkeypatch.setattr(engine.tools, "call", upstream)
    denied = await engine.invoke(
        identity,
        ToolCall(
            tool="knowledge.search", arguments={"query": "ACME-DEMO-1234"}
        ),
    )
    assert denied.reason == "input_sensitive_data"
    assert not denied.upstream_executed and not attempts
    allowed = await engine.invoke(
        identity,
        ToolCall(
            tool="knowledge.search", arguments={"query": "ordinary report"}
        ),
    )
    assert allowed.decision == "redacted" and allowed.upstream_executed
    assert allowed.output == {"nested": [MARKER]}
    audit = json.dumps(engine.ledger.audit())
    assert "ACME-DEMO-1234" not in audit
    assert "PROJECT ORCHID INTERNAL" not in audit


@pytest.mark.parametrize(
    "definition",
    [
        "denylist=(re.compile(r'(?=(ACME-[0-9]+))'),)",
        "denylist=(re.compile(r'OTHER-[0-9]+'),)\n def analyze_string(self,string): yield 'ACME-1234'",
    ],
)
@pytest.mark.parametrize("direction", ["input", "output"])
def test_uncovered_or_zero_width_regex_candidates_fail_closed(
    app, tmp_path, definition, direction
):
    source = (
        "import re\nfrom detect_secrets.plugins.base import RegexBasedDetector\n"
        "class BrokenSpan(RegexBasedDetector):\n secret_type='x'\n "
        + definition
    )
    detector = OfflineSecrets((plugin(tmp_path, source),))
    with pytest.raises(RejectedError) as caught:
        inspect_privacy(
            "ACME-1234",
            app.state.engine.policies.snapshot(),
            direction,
            detector,
        )
    assert caught.value.reason == f"{direction}_secret_detector_unavailable"
