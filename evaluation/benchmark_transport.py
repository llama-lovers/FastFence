"""Measure actual HTTP/MCP transport with real controls and simulated 15ms tools."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

if __package__:
    from evaluation.benchmark_gateway import hardware
    from evaluation.transport_harness import (
        Transport,
        agent_client,
        isolated_gateway,
    )
    from evaluation.transport_measurements import (
        Proof,
        Workload,
        measure,
        summary,
    )
else:
    from benchmark_gateway import hardware
    from transport_harness import Transport, agent_client, isolated_gateway
    from transport_measurements import Proof, Workload, measure, summary


def workloads(size: str, rules: int) -> list[Workload]:
    padding = (
        "Approved quarterly business summary "
        if size == "short"
        else ("Approved business summary " * 310)[:8000]
    )
    result = [
        Workload(
            name="allowed_business",
            query=padding,
            decision="allowed",
            reason="controls_passed",
        ),
        Workload(
            name="blocked_historical_signature",
            query=("pickle.loads( " + padding)[:8192],
            decision="blocked",
            reason="attack_signature",
        ),
    ]
    if rules:
        result.append(
            Workload(
                name="blocked_authored_rule",
                query=(f"blocked-marker-{rules - 1:02} " + padding)[:8192],
                decision="blocked",
                reason="input_text_rule",
            )
        )
    return result


async def run_configuration(
    rules: int, samples: int, warmup: int
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    proof = Proof()
    with isolated_gateway(rules) as gateway:
        for protocol in ["http", "mcp"]:
            async with agent_client(gateway) as client:
                transport = Transport(client, protocol)
                await transport.initialize()
                for concurrency in [1, 8]:
                    await measure(transport.baseline, warmup, concurrency)
                    timings, seconds = await measure(
                        transport.baseline, samples, concurrency
                    )
                    rows.append(
                        {
                            "protocol": protocol,
                            "rules": rules,
                            "concurrency": concurrency,
                            "workload": "unprotected_health"
                            if protocol == "http"
                            else "authenticated_mcp_ping",
                            "scope": "Non-equivalent transport/routing baseline, no business execution; never subtracted",
                            "warmup_excluded_from_timing": warmup,
                            **summary(timings, seconds),
                        }
                    )
                    for size in ["short", "near_tool_limit"]:
                        for workload in workloads(size, rules):

                            async def invoke(
                                selected: Workload = workload,
                                selected_transport: Transport = transport,
                            ) -> dict:
                                return await selected_transport.invoke(
                                    selected.query
                                )

                            def validate(
                                verdict: dict, selected: Workload = workload
                            ) -> None:
                                proof.record(verdict, selected)

                            await measure(invoke, warmup, concurrency, validate)
                            timings, seconds = await measure(
                                invoke, samples, concurrency, validate
                            )
                            rows.append(
                                {
                                    "protocol": protocol,
                                    "rules": rules,
                                    "concurrency": concurrency,
                                    "workload": workload.name,
                                    "payload_class": size,
                                    "query_utf8_bytes": len(
                                        workload.query.encode()
                                    ),
                                    "warmup_excluded_from_timing_but_in_accounting": warmup,
                                    "expected_decision": workload.decision,
                                    "expected_reason": workload.reason,
                                    "upstream": "actual simulated DemoTools with intentional 15ms sleep"
                                    if workload.decision == "allowed"
                                    else "not executed",
                                    **summary(timings, seconds),
                                }
                            )
        async with httpx.AsyncClient(
            base_url=gateway.url,
            trust_env=False,
            timeout=15,
            headers={
                "Authorization": f"Bearer {gateway.tokens['security-admin']}"
            },
        ) as admin:
            status_response = await admin.get("/api/admin/status")
            status_response.raise_for_status()
            export = await admin.get("/api/admin/audit.jsonl")
            export.raise_for_status()
            if any(token in export.text for token in gateway.tokens.values()):
                raise ValueError(
                    "Private credentials appeared in exported audit"
                )
            status = status_response.json()
            audit = [json.loads(line) for line in export.text.splitlines()]
            proof.verify(status, audit)
            if any(
                {"output", "prompt", "arguments"}.intersection(row)
                for row in audit
            ):
                raise ValueError("Audit unexpectedly contains payload bodies")
    return rows, {
        "rules": rules,
        "total_invocations_including_warmup": proof.invocations,
        "allowed_budget_calls_including_warmup": proof.calls,
        "settled_token_units": proof.tokens,
        "settled_cost_microusd": proof.cost,
        "policy_feed_versions": sorted(proof.versions),
        "audit_count": len(audit),
        "all_verdicts_verified": True,
        "accounting_verified": True,
        "audit_verified": True,
        "semantic_calls": 0,
        "pending_reservations": 0,
    }


async def run(samples: int, warmup: int) -> dict:
    rows, checks = [], []
    for rules in [0, 1, 64]:
        results, proof = await run_configuration(rules, samples, warmup)
        rows.extend(results)
        checks.append(proof)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "environment": hardware(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in [
                "fastfence",
                "fastapi",
                "fastmcp",
                "httpx",
                "detect-secrets",
            ]
        },
        "scope": "Actual uvicorn subprocess, loopback TCP, persistent HTTP connections and genuine JSON-RPC MCP protocol; complete deterministic pipeline including detect-secrets and authored text rules",
        "upstream": "SIMULATED DemoTools, intentional15ms delay; no LLM/semantic inference",
        "measurement": "Per-request timer starts after concurrency permit, includes serialization/transport/server/response decode, excludes invariant checks; throughput includes client scheduling and checks; connection/handshake excluded after setup; warmup consumes audit/budgets",
        "limitations": [
            "Local development hardware, power state and other processes uncontrolled",
            "Concurrency uses a single client event loop and one uvicorn worker; no production/global scaling claim",
            "Health/ping are non-equivalent baseline operations; no subtraction yields pure control overhead",
            "Results combine network, application, actual controls and simulated business latency",
        ],
        "configuration_checks": checks,
        "results": rows,
        "all_passed": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 10 or args.warmup < 1 or args.samples + args.warmup > 400:
        parser.error(
            "Require samples>=10, warmup>=1, samples+warmup<=400 for complete audit retention"
        )
    report = asyncio.run(run(args.samples, args.warmup))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"PASS: {len(report['results'])} real transport groups; {args.output}"
    )
