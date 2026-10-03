"""Synthetic acceptance cases executed inside the isolated installed environment."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from acp_sdk.client import Client
from acp_sdk.models import Message, MessagePart


async def verify(url, upstream_url):
    root = Path("state/examples/acp-gateway")
    credentials = json.loads((root / "state/credentials.json").read_text())
    agent_headers = {"Authorization": "Bearer " + credentials["local-agent"]}
    admin_headers = {"Authorization": "Bearer " + credentials["local-admin"]}
    observations = []
    async with httpx.AsyncClient(
        base_url=url, trust_env=False, timeout=10
    ) as http:
        for headers, expected in (({}, 401), (admin_headers, 403)):
            response = await http.post(
                "/acp/runs", headers=headers, content=b"invalid json"
            )
            assert response.status_code == expected, response.text
        observations.append(
            "unauthorized and management identities denied before body parsing"
        )
        response = await http.get(upstream_url + "/agents")
        assert response.status_code == 401
        observations.append("direct upstream refuses unauthenticated clients")
        async with Client(
            base_url=url + "/acp",
            headers=agent_headers,
            trust_env=False,
            timeout=20,
        ) as client:
            agents = [agent.name async for agent in client.agents()]
            assert agents == ["uppercase"], agents

            async def invoke(text):
                return await client.run_sync(
                    agent="uppercase",
                    input=[
                        Message(role="user", parts=[MessagePart(content=text)])
                    ],
                )

            result = await invoke("hello")
            assert result.status.value == "completed", result
            assert result.output[0].parts[0].content == "HELLO"
            observations.append(
                "official ACP SDK client -> gateway -> official SDK agent completes actual uppercase operation"
            )

            result = await invoke("forbidden")
            assert result.status.value == "failed" and not result.output
            assert result.error.data["reason"] == "input_text_rule"
            assert result.error.data["upstream_executed"] is False
            observations.append(
                "input denial is failed ACP run with no output and no upstream execution"
            )

            result = await invoke("secret output")
            assert result.status.value == "completed"
            assert (
                result.output[0].parts[0].content == "[REDACTED:detect_secrets]"
            )
            observations.append(
                "output-only custom detector redacts actual upstream response"
            )

            async def update(edit):
                response = await http.get(
                    "/api/admin/status", headers=admin_headers
                )
                response.raise_for_status()
                policy = response.json()["policy"]
                policy["version"] += 1
                edit(policy)
                response = await http.put(
                    "/api/admin/policy", headers=admin_headers, json=policy
                )
                response.raise_for_status()

            def output_rule(policy):
                policy["text_rules"].append(
                    {
                        "id": "output-only-package-test",
                        "operator": "equals",
                        "value": "HELLO",
                        "case_sensitive": True,
                        "direction": "output",
                        "target": "tool",
                    }
                )

            await update(output_rule)
            result = await invoke("hello")
            assert result.status.value == "failed" and not result.output
            assert result.error.data["reason"] == "output_text_rule"
            assert result.error.data["upstream_executed"] is True
            observations.append(
                "output denial withholds actual upstream result and reports execution"
            )

            def reversible(policy):
                policy["text_rules"] = [
                    rule
                    for rule in policy["text_rules"]
                    if rule["id"] != "output-only-package-test"
                ]
                policy["anonymization"] = {
                    "enabled": True,
                    "mode": "reversible",
                    "rules": [
                        {
                            "id": "output-name",
                            "operator": "literal",
                            "value": "HELLO",
                            "replacement": "PERSON",
                            "direction": "output",
                            "target": "tool",
                            "allow_restore": True,
                        }
                    ],
                }

            await update(reversible)
            result = await invoke("hello")
            assert result.status.value == "completed"
            assert result.output[0].parts[0].content.startswith("[FFR1.")
            async with Client(
                base_url=url + "/acp",
                headers={
                    **agent_headers,
                    "X-FastFence-Restore-Originals": "true",
                },
                trust_env=False,
            ) as restore_client:
                result = await restore_client.run_sync(
                    agent="uppercase",
                    input=[
                        Message(
                            role="user", parts=[MessagePart(content="hello")]
                        )
                    ],
                )
                assert result.status.value == "completed"
                assert result.output[0].parts[0].content == "HELLO"
            observations.append(
                "reversible output remains opaque by default and restores only with request opt-in"
            )
        response = await http.get(
            "/api/admin/audit.jsonl", headers=admin_headers
        )
        response.raise_for_status()
        assert (
            "SECRET OUTPUT" not in response.text
            and "[FFR1." not in response.text
        )
        observations.append(
            "audit excludes sensitive output and recovery token payloads"
        )
    report = {
        "status": "passed",
        "acp_sdk": "1.0.3",
        "transport": "actual loopback HTTP",
        "checks": observations,
        "count": len(observations),
        "model_inference": False,
    }
    Path("acp-package-report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("upstream_url")
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.upstream_url))
