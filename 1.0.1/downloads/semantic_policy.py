"""Preview a named natural-language rule with real Laya; activate only explicitly."""

import argparse
import copy
import difflib
import json
import os
from pathlib import Path

import httpx
import yaml

from fastfence.modules.control.domain.models import Policy

RULE = {
    "id": "no-personal-financial-advice",
    "instruction": "Block personalized financial recommendations. General financial definitions are allowed.",
    "direction": "input",
    "target": "model",
}
CASES = [
    ("Buy this stock immediately with all your savings.", "blocked"),
    ("Define a stock as a financial instrument.", "no_semantic_block"),
]


def admin_token(path: Path) -> str:
    if value := os.environ.get("FASTFENCE_ADMIN_TOKEN"):
        return value
    if path == Path("state/credentials.json") and not path.exists():
        path = Path("state/demo-tokens.json")
    values = json.loads(path.read_text())
    return values.get("local-admin") or values["security-admin"]


def read_policy(client: httpx.Client, token: str) -> dict:
    response = client.get(
        "/api/admin/status", headers={"Authorization": "Bearer " + token}
    )
    response.raise_for_status()
    return response.json()["policy"]


def prepare(client: httpx.Client, token: str) -> tuple[dict, dict, list[dict]]:
    base = read_policy(client, token)
    candidate = copy.deepcopy(base)
    candidate["version"] += 1
    semantic = candidate["semantic"]
    if semantic["provider"] != "laya":
        semantic.update(
            provider="laya",
            model="qwen3:4b",
            timeout_ms=max(30000, semantic["timeout_ms"]),
        )
    semantic["rules"] = [
        rule for rule in semantic.get("rules", []) if rule["id"] != RULE["id"]
    ] + [RULE]
    candidate = Policy.model_validate(candidate).model_dump(mode="json")
    results = []
    for text, expected in CASES:
        response = client.post(
            "/api/admin/semantic/preview",
            headers={"Authorization": "Bearer " + token},
            json={
                "rule": RULE,
                "text": text,
                "direction": "input",
                "target": "model",
                "base_version": base["version"],
            },
        )
        response.raise_for_status()
        result = response.json()
        results.append({"expected": expected, **result})
    return base, candidate, results


def activate(
    client: httpx.Client,
    token: str,
    base: dict,
    candidate: dict,
    results: list[dict],
) -> dict:
    if len(results) != len(CASES) or not all(
        result["decision"] == result["expected"] and result["rule_applied"]
        for result in results
    ):
        raise ValueError(
            "Preview did not match expected classifications; no activation."
        )
    if read_policy(client, token) != base:
        raise ValueError(
            "Active policy changed; preview again before activation."
        )
    response = client.put(
        "/api/admin/policy",
        headers={"Authorization": "Bearer " + token},
        json=candidate,
    )
    response.raise_for_status()  # Server also rejects version/source conflicts.
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--credentials", type=Path, default=Path("state/credentials.json")
    )
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    token = admin_token(args.credentials)
    with httpx.Client(
        base_url=args.url, timeout=120, trust_env=False
    ) as client:
        base, candidate, results = prepare(client, token)
        print(
            "".join(
                difflib.unified_diff(
                    yaml.safe_dump(base, sort_keys=False).splitlines(
                        keepends=True
                    ),
                    yaml.safe_dump(candidate, sort_keys=False).splitlines(
                        keepends=True
                    ),
                    fromfile="active-policy.yaml",
                    tofile="candidate-policy.yaml",
                )
            )
        )
        print(json.dumps(results, indent=2))
        if args.activate:
            print(json.dumps(activate(client, token, base, candidate, results)))
        else:
            print(
                "Preview only. Review the diff; rerun with --activate to apply."
            )


if __name__ == "__main__":
    main()
