"""Actual Laya policy proposals plus isolated real controls, with sanitized evidence."""

import argparse
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from fastfence.shared.settings.app_settings import AppSettings

if __package__:
    from evaluation.business_fixture import create_app, initialize
else:
    from business_fixture import create_app, initialize


def run(root: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix="fastfence-policy-operations-"
    ) as directory:
        temporary = Path(directory)
        (temporary / "config").mkdir()
        shutil.copy(
            root / "examples/business_tools/policy.yaml",
            temporary / "config/policy.yaml",
        )
        shutil.copy(
            root / "config/signatures.json",
            temporary / "config/signatures.json",
        )
        initialize(temporary / "state")
        tokens = json.loads((temporary / "state/demo-tokens.json").read_text())
        app = create_app(AppSettings(root=temporary, authoring_root=root))
        with TestClient(app) as client:
            admin = {"Authorization": f"Bearer {tokens['security-admin']}"}
            analyst = {"Authorization": f"Bearer {tokens['analyst-blue']}"}
            operator = {"Authorization": f"Bearer {tokens['operator-blue']}"}
            instructions = [
                (
                    "selective_email_input",
                    "Redaguj tylko adresy e-mail w wejściu agenta. Pozostałe ustawienia prywatności, hasła, sekrety, PESEL i wyjście pozostaw bez zmian.",
                    {
                        "type": "set_privacy_detector",
                        "detector": "pii_email",
                        "direction": "input",
                        "action": "redact",
                    },
                ),
                (
                    "restrict_tool_roles",
                    "Pozwól korzystać z narzędzia knowledge.search tylko użytkownikom z rolą operator. Nie zmieniaj pozostałych narzędzi ani limitów.",
                    {
                        "type": "restrict_tool_roles",
                        "tool": "knowledge.search",
                        "roles": ["operator"],
                    },
                ),
            ]
            version = 1
            for label, instruction, expected in instructions:
                response = client.post(
                    "/api/admin/policies/draft",
                    headers=admin,
                    json={"instruction": instruction, "base_version": version},
                )
                if response.status_code != 200:
                    cases.append(
                        {
                            "name": label,
                            "passed": False,
                            "status": response.status_code,
                            "error": response.json().get("detail"),
                        }
                    )
                    break
                proposal = response.json()
                exact = proposal["operations"] == [expected]
                if not exact:
                    cases.append(
                        {
                            "name": label,
                            "passed": False,
                            "error": "proposal_semantics_mismatch",
                            "operation_types": [
                                op["type"] for op in proposal["operations"]
                            ],
                            "actual_operations": proposal["operations"],
                            "expected_operation": expected,
                        }
                    )
                    break
                preview = client.post(
                    "/api/admin/policies/preview",
                    headers=admin,
                    json={
                        "proposal_id": proposal["proposal_id"],
                        "samples": [
                            {
                                "target": "tool",
                                "direction": "input",
                                "text": "anna@example.org",
                            }
                        ],
                    },
                )
                activation = client.post(
                    "/api/admin/policies/activate",
                    headers=admin,
                    json={
                        "proposal_id": proposal["proposal_id"],
                        "base_version": version,
                    },
                )
                success = (
                    preview.status_code == 200 and activation.status_code == 200
                )
                cases.append(
                    {
                        "name": label,
                        "passed": success,
                        "source": proposal["source"],
                        "model": proposal["model"],
                        "operations": proposal["operations"],
                        "inference_ms": proposal["inference_ms"],
                        "preview_status": preview.status_code,
                        "activation_status": activation.status_code,
                        "activation_inference_calls": 0,
                    }
                )
                if not success:
                    break
                version = activation.json()["policy_version"]
                checks = (
                    [
                        (
                            "email_redacted",
                            "anna@example.org",
                            analyst,
                            "redacted",
                            True,
                        ),
                        (
                            "other_pii_still_blocked",
                            "anna@example.org 12345678901",
                            analyst,
                            "blocked",
                            False,
                        ),
                    ]
                    if label == "selective_email_input"
                    else [
                        (
                            "excluded_role_denied",
                            "Quarterly forecast",
                            analyst,
                            "blocked",
                            False,
                        ),
                        (
                            "retained_role_allowed",
                            "Quarterly forecast",
                            operator,
                            "allowed",
                            True,
                        ),
                    ]
                )
                for name, query, identity, decision, upstream in checks:
                    verdict = client.post(
                        "/api/invoke",
                        headers=identity,
                        json={
                            "tool": "knowledge.search",
                            "arguments": {"query": query},
                        },
                    ).json()
                    cases.append(
                        {
                            "name": name,
                            "passed": verdict["decision"] == decision
                            and verdict["upstream_executed"] == upstream,
                            "decision": verdict["decision"],
                            "reason": verdict["reason"],
                            "upstream_executed": verdict["upstream_executed"],
                            "request_id": verdict["request_id"],
                        }
                    )
            audit = client.get("/api/admin/audit.jsonl", headers=admin).text
            sanitized = all(
                value not in audit
                for value in [
                    *tokens.values(),
                    "anna@example.org",
                    "12345678901",
                ]
            )
            cases.append({"name": "sanitized_audit", "passed": sanitized})
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "cases": cases,
        "all_passed": all(case["passed"] for case in cases),
        "scope": "Actual pinned Laya/local Qwen management authoring; isolated gateway, real deterministic controls, simulated business tools. No activation inference.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    report = run(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "all_passed": report["all_passed"],
                "case_count": len(report["cases"]),
            }
        )
    )
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
