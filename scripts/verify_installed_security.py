"""Run existing offline security regressions against an exact public distribution."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

if __package__:
    from .benchmark_package import clean_environment
else:
    from benchmark_package import clean_environment

TEST_FILES = (
    "tests/integration/test_gateway.py",
    "tests/integration/test_secret_controls.py",
    "tests/integration/test_redaction_composition.py",
    "tests/integration/test_text_rule_controls.py",
    "tests/integration/test_policy_validation.py",
    "tests/integration/test_policy_source_conflict.py",
    "tests/unit/test_budgets.py",
    "tests/unit/test_signature_matching.py",
    "tests/unit/test_semantic_restoration.py",
    "tests/unit/test_custom_secret_plugins.py",
)
FIXTURES = (
    "tests/__init__.py",
    "tests/conftest.py",
    "tests/integration/__init__.py",
    "tests/unit/__init__.py",
    "tests/fixtures/__init__.py",
    "tests/fixtures/auth.py",
    "tests/fixtures/configuration.py",
    "tests/fixtures/policy.py",
    "tests/fixtures/secrets.py",
    "examples/business_tools/tools.py",
    "examples/business_tools/credentials.py",
    "examples/business_tools/policy.yaml",
    "examples/docs/custom_detector.py",
    "config/signatures.json",
    "evaluation/historical_attacks.json",
    "scripts/installed_security_probe.py",
)


def stage(source, root):
    hashes = {}
    for name in (*TEST_FILES, *FIXTURES):
        original = (source / name).resolve()
        if (
            not original.is_relative_to(source.resolve())
            or not original.is_file()
        ):
            raise ValueError("Missing or external security fixture")
        content = original.read_bytes()
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    (root / "pytest.ini").write_text(
        "[pytest]\nasyncio_mode=auto\nasyncio_default_fixture_loop_scope=function\n"
    )
    return hashes


def execute(command, root, environment, timeout=900):
    result = subprocess.run(
        command, cwd=root, env=environment, capture_output=True, timeout=timeout
    )
    if result.returncode:
        raise RuntimeError(
            "Installed security setup failed; subprocess details withheld"
        )


def verify(version, output):
    import re

    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Use an exact public stable version")
    source = Path(__file__).resolve().parents[1]
    environment = clean_environment()
    with tempfile.TemporaryDirectory(
        prefix="fastfence-installed-security-"
    ) as directory:
        root = Path(directory)
        if root.is_relative_to(source):
            raise ValueError("Verification must run outside the checkout")
        hashes = stage(source, root)
        execute(
            [
                "uv",
                "--no-config",
                "venv",
                "--python",
                "3.12",
                str(root / "venv"),
            ],
            root,
            environment,
        )
        python = root / "venv/bin/python"
        execute(
            [
                "uv",
                "--native-tls",
                "--no-config",
                "pip",
                "install",
                "--python",
                str(python),
                "--default-index",
                "https://pypi.org/simple",
                "--refresh-package",
                "fastfence",
                f"fastfence=={version}",
                "pytest>=8.4.1,<9",
                "pytest-asyncio>=1,<2",
            ],
            root,
            environment,
        )
        environment.update(
            VERIFY_VERSION=version,
            VERIFY_SOURCE=str(source),
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        )
        execute(
            [
                str(python),
                "-c",
                "from scripts import installed_security_probe as p; p.provenance()",
            ],
            root,
            environment,
        )
        process = subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                "-c",
                str(root / "pytest.ini"),
                "-p",
                "pytest_asyncio.plugin",
                "-p",
                "scripts.installed_security_probe",
                "--tb=no",
                "-q",
                *TEST_FILES,
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            timeout=180,
        )
        result_path = root / "security-results.json"
        if not result_path.is_file():
            raise RuntimeError(
                "Security pytest did not produce verified evidence"
            )
        report = json.loads(result_path.read_text())
        counts = {
            name: sum(row["outcome"] == name for row in report["results"])
            for name in ("passed", "failed", "skipped")
        }
        report.update(
            created_at=datetime.now(UTC).isoformat(),
            installation="public_pypi_fresh_external_venv",
            scope="Existing offline unit and in-process integration security regressions against the public installed package; synthetic tools and mocked semantic boundaries; no real model inference or model accuracy claim.",
            fixture_sha256=hashes,
            summary=counts,
            provenance_checked_before_and_after=True,
            network="Real socket connections disabled in the pytest process; HTTP integration uses in-process TestClient/MockTransport.",
            limitations=[
                "These 143 parameterized existing cases are not 143 independent novel attacks.",
                "Semantic failure/restoration behavior uses mocked assessments, not classification accuracy.",
                "This suite does not exercise external HTTP/MCP transport; the separate public package operator smoke supplies live HTTP evidence.",
            ],
        )
        success = (
            process.returncode == 0
            and report["exit_code"] == 0
            and report["collected"] == 143
            and counts == {"passed": 143, "failed": 0, "skipped": 0}
        )
        report["status"] = "passed" if success else "failed"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        if not success:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "collected": report["collected"],
                        "summary": counts,
                        "failures": [
                            r
                            for r in report["results"]
                            if r["outcome"] != "passed"
                        ],
                    }
                )
            )
            raise RuntimeError(
                "Installed security suite failed; see sanitized report"
            )
    print(
        json.dumps(
            {
                "status": "passed",
                "version": version,
                "summary": counts,
                "report": str(output),
            }
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(args.version, args.output)
