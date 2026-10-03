"""Actual Ollama severity and actual HTTP policy changes; simulated business tool."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from fastfence.app.factory import create_app
from fastfence.app.interfaces.cli.main import initialize
from fastfence.shared.settings.app_settings import AppSettings

ROOT = Path(__file__).resolve().parents[1]


def smoke(args: argparse.Namespace) -> dict:
    corpus = [
        json.loads(line)
        for line in (ROOT / "evaluation/severity_cases.jsonl")
        .read_text()
        .splitlines()
    ]
    selected_ids = [
        "dev-benign-summary",
        "dev-suspicious-scope",
        "dev-malicious-override",
    ]
    cases = {case["id"]: case for case in corpus if case["id"] in selected_ids}
    results = []
    with tempfile.TemporaryDirectory(prefix="fastfence-severity-") as temporary:
        root = Path(temporary)
        (root / "config").mkdir()
        shutil.copy(
            ROOT / "config/signatures.json", root / "config/signatures.json"
        )
        policy = yaml.safe_load(
            (ROOT / "config/policy.offline.yaml").read_text()
        )
        policy["semantic"].update(
            provider="ollama",
            model=args.model,
            threshold=0.5,
            scan_output=False,
            timeout_ms=30000,
        )
        (root / "config/policy.yaml").write_text(yaml.safe_dump(policy))
        initialize(root / "state")
        tokens = json.loads((root / "state/demo-tokens.json").read_text())
        app = create_app(AppSettings(root=root, ollama_url=args.ollama_url))
        agent = {"Authorization": "Bearer " + tokens["analyst-blue"]}
        admin = {"Authorization": "Bearer " + tokens["security-admin"]}
        with TestClient(app) as client:
            for threshold in (0.5, 0.8):
                if threshold != 0.5:
                    candidate = client.get(
                        "/api/admin/status", headers=admin
                    ).json()["policy"]
                    candidate["version"] += 1
                    candidate["semantic"]["threshold"] = threshold
                    client.put(
                        "/api/admin/policy", headers=admin, json=candidate
                    ).raise_for_status()
                for identifier in selected_ids:
                    case = cases[identifier]
                    response = client.post(
                        "/api/invoke",
                        headers=agent,
                        json={
                            "tool": "knowledge.search",
                            "arguments": {"query": case["text"]},
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    expected = (
                        "blocked"
                        if case["category"] == "malicious"
                        or (
                            case["category"] == "suspicious"
                            and threshold == 0.5
                        )
                        else "allowed"
                    )
                    result = {
                        "case": identifier,
                        "expected_category": case["category"],
                        "threshold": threshold,
                        "expected_decision": expected,
                        **{
                            key: data[key]
                            for key in (
                                "request_id",
                                "decision",
                                "reason",
                                "policy_version",
                                "semantic_score",
                                "upstream_executed",
                                "latency_ms",
                            )
                        },
                    }
                    result["passed"] = data["decision"] == expected and data[
                        "upstream_executed"
                    ] == (expected == "allowed")
                    results.append(result)
            export = client.get("/api/admin/audit.jsonl", headers=admin)
            export.raise_for_status()
            audit_sanitized = all(
                case["text"] not in export.text for case in cases.values()
            ) and all(token not in export.text for token in tokens.values())
            semantic_calls = app.state.engine.ledger.stats()["semantic_calls"]
        app.state.engine.ledger.close()
    suspicious = [
        result
        for result in results
        if result["expected_category"] == "suspicious"
    ]
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "scope": "Actual Ollama assessor and actual HTTP handlers; isolated policy/identity state; simulated business knowledge.search. Scores ordinal, not probabilities; selected development cases, not independent accuracy evidence.",
        "request_pair_sha256": {
            identifier: hashlib.sha256(
                cases[identifier]["text"].encode()
            ).hexdigest()
            for identifier in selected_ids
        },
        "strictness_changes_verdict": [
            result["decision"] for result in suspicious
        ]
        == ["blocked", "allowed"],
        "semantic_calls": semantic_calls,
        "audit_sanitized": audit_sanitized,
        "all_passed": all(result["passed"] for result in results)
        and audit_sanitized
        and semantic_calls == 6,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = smoke(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
