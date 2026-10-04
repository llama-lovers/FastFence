"""Review semantic expectations with Laya; activate explicitly or replay saved tests."""

import argparse
import json
import os
from pathlib import Path

import httpx

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


def prepare(client: httpx.Client, token: str) -> dict:
    base = read_policy(client, token)
    directions = (
        ("input", "output")
        if RULE["direction"] == "both"
        else (RULE["direction"],)
    )
    targets = (
        ("model", "tool") if RULE["target"] == "all" else (RULE["target"],)
    )
    cases = [
        {
            "id": f"sample-{index}-{direction}-{target}",
            "text": text,
            "direction": direction,
            "target": target,
            "expected": expected,
        }
        for index, (text, expected) in enumerate(CASES, start=1)
        for direction in directions
        for target in targets
    ]
    response = client.post(
        "/api/admin/semantic/review",
        headers={"Authorization": "Bearer " + token},
        json={"base_version": base["version"], "rule": RULE, "cases": cases},
    )
    response.raise_for_status()
    return response.json()


def activate(client: httpx.Client, token: str, review: dict) -> dict:
    if not review.get("tests_passed") or not review.get("review_id"):
        raise ValueError(
            "Review failed expected classifications; no activation."
        )
    response = client.post(
        "/api/admin/semantic/activate",
        headers={"Authorization": "Bearer " + token},
        json={
            "review_id": review["review_id"],
            "base_version": review["base_version"],
            "confirmed": True,
        },
    )
    # The server binds the receipt to exact cases, policy, feed and administrator.
    response.raise_for_status()
    return response.json()


def replay(client: httpx.Client, token: str) -> dict:
    base = read_policy(client, token)
    suite = client.get(
        "/api/admin/semantic/tests",
        headers={"Authorization": "Bearer " + token},
    )
    suite.raise_for_status()
    response = client.post(
        "/api/admin/semantic/tests/replay",
        headers={"Authorization": "Bearer " + token},
        json={
            "base_version": base["version"],
            "suite_digest": suite.json()["suite_digest"],
        },
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--credentials", type=Path, default=Path("state/credentials.json")
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--activate", action="store_true")
    actions.add_argument("--replay-tests", action="store_true")
    args = parser.parse_args()
    token = admin_token(args.credentials)
    with httpx.Client(
        base_url=args.url, timeout=130, trust_env=False
    ) as client:
        if args.replay_tests:
            result = replay(client, token)
            print(json.dumps(result, indent=2))
            if not result["tests_passed"]:
                raise SystemExit(2)
            return
        review = prepare(client, token)
        print(review["yaml_diff"])
        print(json.dumps(review["cases"], indent=2))
        if not review["tests_passed"]:
            print(
                "Expectations failed or assessment incomplete. Nothing activated."
            )
            raise SystemExit(2)
        if args.activate:
            result = activate(client, token, review)
            print(json.dumps(result))
            if not result.get("tests_saved", False):
                print(
                    "Policy activated, but tests were not saved. Do not repeat activation."
                )
                raise SystemExit(2)
        else:
            print(
                "Review only. Inspect the diff; rerun with --activate to apply."
            )


if __name__ == "__main__":
    main()
