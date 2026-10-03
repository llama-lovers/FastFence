"""Bounded real HTTP/MCP soak during valid and failed atomic bundle refreshes."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

if __package__:
    from evaluation.benchmark_gateway import hardware
    from evaluation.soak_harness import isolated_soak, rss_sample
    from evaluation.soak_proof import Generation, SoakProof
    from evaluation.transport_harness import Transport, agent_client
else:
    from benchmark_gateway import hardware
    from soak_harness import isolated_soak, rss_sample
    from soak_proof import Generation, SoakProof
    from transport_harness import Transport, agent_client

CASES = [
    ("allowed", "knowledge.search", {"query": "Quarterly governance plan"}),
    ("signature", "knowledge.search", {"query": "pickle.loads("}),
    (
        "sensitive_input",
        "knowledge.search",
        {"query": "Email anna@example.org"},
    ),
    ("output_redaction", "report.contact", {}),
    ("rbac", "payments.prepare", {"amount": 100, "recipient": "vendor"}),
    (
        "dynamic_signature",
        "knowledge.search",
        {"query": "soak-restricted-marker"},
    ),
]


def generation(bundle: dict) -> Generation:
    return Generation(
        policy_version=bundle["policy"]["version"],
        feed_version=bundle["feed"]["version"],
        input_action=bundle["policy"]["privacy"]["input"],
        dynamic_signature=any(
            row["id"] == "soak_marker" for row in bundle["feed"]["signatures"]
        ),
    )


async def status(client: httpx.AsyncClient) -> dict:
    response = await client.get("/api/admin/status")
    response.raise_for_status()
    return response.json()


async def await_refresh(client, pair, failure_count=None) -> dict:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = await status(client)
        observed = (current["policy"]["version"], current["feed"]["version"])
        if failure_count is not None and observed != pair:
            raise ValueError("Invalid candidate replaced the last valid bundle")
        refreshed = (
            current["configuration"]["refresh_failures"] > failure_count
            if failure_count is not None
            else observed == pair
        )
        if refreshed:
            return current
        await asyncio.sleep(0.05)
    raise ValueError(
        "Background configuration update did not become observable"
    )


async def update_sources(
    admin, source, original, proof, seconds, stop, started
):
    active = copy.deepcopy(original)
    evidence = []
    for index, action in enumerate(
        ["valid", "invalid", "valid", "rollback", "valid", "oversize", "valid"],
        1,
    ):
        if stop.is_set():
            break
        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=max(
                    0.001, seconds * index / 8 - (time.monotonic() - started)
                ),
            )
            break
        except TimeoutError:
            pass
        previous = await status(admin)
        pair = (active["policy"]["version"], active["feed"]["version"])
        if action == "valid":
            active["policy"]["version"] += 1
            active["feed"]["version"] += 1
            active["policy"]["privacy"]["input"] = (
                "redact"
                if active["policy"]["privacy"]["input"] == "block"
                else "block"
            )
            signatures = [
                row
                for row in active["feed"]["signatures"]
                if row["id"] != "soak_marker"
            ]
            if active["policy"]["privacy"]["input"] == "redact":
                signatures.append(
                    {
                        "id": "soak_marker",
                        "pattern": "soak-restricted-marker",
                        "description": "Synthetic dynamic soak marker",
                    }
                )
            active["feed"]["signatures"] = signatures
            prepared = generation(active)
            proof.register(prepared)
            pair = (prepared.policy_version, prepared.feed_version)
            source.publish(json.dumps(active).encode())
            observed = await await_refresh(admin, pair)
        else:
            body = (
                b" " * 262_145
                if action == "oversize"
                else json.dumps(
                    original
                    if action == "rollback"
                    else {"policy": {}, "feed": active["feed"]}
                ).encode()
            )
            source.publish(body)
            observed = await await_refresh(
                admin, pair, previous["configuration"]["refresh_failures"]
            )
        expected_error = {
            "valid": None,
            "invalid": "invalid_or_unavailable_bundle",
            "rollback": "version_conflict",
            "oversize": "source_too_large",
        }[action]
        if observed["configuration"]["last_error"] != expected_error:
            raise ValueError("Unexpected configuration failure classification")
        evidence.append(
            {
                "step": index,
                "candidate": action,
                "policy_version": pair[0],
                "feed_version": pair[1],
                "last_error": observed["configuration"]["last_error"],
                "generation": observed["configuration"]["generation"],
            }
        )
    return evidence


async def invoke(transport, tool, arguments):
    body = {"tool": tool, "arguments": arguments}
    if transport.protocol == "mcp":
        result = await transport.rpc(
            "tools/call", {"name": "invoke", "arguments": body}
        )
        if result.get("isError"):
            raise ValueError("MCP invocation error invalidates soak")
        return result["structuredContent"]
    response = await transport.client.post("/api/invoke", json=body)
    response.raise_for_status()
    return response.json()


async def sample_memory(samples, pid, started, stop):
    while not stop.is_set():
        samples.append(
            {
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "rss_bytes": await asyncio.to_thread(rss_sample, pid),
            }
        )
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except TimeoutError:
            pass


async def run(seconds: float, concurrency: int = 8) -> dict:
    proof, samples = SoakProof(), []
    stop = asyncio.Event()
    with isolated_soak() as (gateway, source, bundle):
        proof.register(generation(bundle))
        async with (
            agent_client(gateway) as agent,
            httpx.AsyncClient(
                base_url=gateway.url,
                trust_env=False,
                timeout=20,
                headers={
                    "Authorization": f"Bearer {gateway.tokens['security-admin']}"
                },
            ) as admin,
        ):
            transports = [
                Transport(agent, "http" if index % 2 == 0 else "mcp")
                for index in range(concurrency)
            ]
            for transport in transports:
                await transport.initialize()
            started = time.monotonic()
            date = datetime.now(UTC).date()

            async def worker(index):
                sequence = index
                while (
                    time.monotonic() - started < seconds and not stop.is_set()
                ):
                    case, tool, arguments = CASES[sequence % len(CASES)]
                    verdict = await invoke(transports[index], tool, arguments)
                    proof.record(verdict, case, transports[index].protocol)
                    sequence += 1

            updater = asyncio.create_task(
                update_sources(
                    admin, source, bundle, proof, seconds, stop, started
                )
            )
            sampler = asyncio.create_task(
                sample_memory(samples, gateway.pid, started, stop)
            )
            workers = [
                asyncio.create_task(worker(index))
                for index in range(concurrency)
            ]
            try:
                completed = await asyncio.gather(*workers, updater)
                updates = completed[-1]
            finally:
                stop.set()
                for task in [*workers, updater, sampler]:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(
                    *workers, updater, sampler, return_exceptions=True
                )
            if (
                sampler.done()
                and not sampler.cancelled()
                and sampler.exception()
            ):
                raise ValueError("RSS sampling failed; report invalidated")
            elapsed = time.monotonic() - started
            if datetime.now(UTC).date() != date:
                raise ValueError(
                    "UTC day rollover invalidates single-day accounting proof"
                )
            final = await status(admin)
            response = await admin.get("/api/admin/audit.jsonl")
            response.raise_for_status()
            if any(token in response.text for token in gateway.tokens.values()):
                raise ValueError("Credential appeared in audit export")
            audit = [json.loads(line) for line in response.text.splitlines()]
            proof.verify(final, audit, gateway.audit_capacity)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "environment": hardware(),
        "scope": "Real loopback TCP HTTP/MCP, trusted local HTTP atomic bundle source, background refresh, actual deterministic controls; simulated15ms business backend; no LLM",
        "requested_duration_seconds": seconds,
        "actual_duration_seconds": round(elapsed, 3),
        "concurrency": concurrency,
        "total_invocations": len(proof.records),
        "decisions": proof.decisions,
        "workloads": proof.workloads,
        "protocols": proof.protocols,
        "throughput_rps": round(len(proof.records) / elapsed, 3),
        "allowed_budget_calls": proof.calls,
        "settled_token_units": proof.tokens,
        "settled_cost_microusd": proof.cost,
        "verified_snapshot_workload_protocol_groups": len(proof.coverage),
        "observed_snapshots": [
            proof.generations[pair].model_dump()
            for pair in sorted(proof.observed_generations)
        ],
        "configuration_updates": updates,
        "configuration_fetches": source.fetches,
        "configuration_refresh_successes": final["configuration"][
            "refresh_successes"
        ],
        "configuration_refresh_failures": final["configuration"][
            "refresh_failures"
        ],
        "final_configuration_error": final["configuration"]["last_error"],
        "engine_tail_p95_latency_ms": final["metrics"]["p95_latency_ms"],
        "audit_capacity": gateway.audit_capacity,
        "audit_retained": len(audit),
        "audit_dropped": final["metrics"]["audit_dropped"],
        "latency_sample_size": final["metrics"]["latency_sample_size"],
        "final_inflight": 0,
        "semantic_calls": 0,
        "rss_samples": samples,
        "rss_min_bytes": min(row["rss_bytes"] for row in samples),
        "rss_max_bytes": max(row["rss_bytes"] for row in samples),
        "all_outcomes_accounting_audit_verified": True,
        "limitations": [
            "Bounded development soak, not proof of leak freedom, production scalability or long-duration stability",
            "RSS includes interpreter/framework caches and is sampled every2seconds; no isolated per-control allocation claim",
            "Single uvicorn worker and local HTTP source; machine power state/other processes uncontrolled",
            "Atomic HTTP bundles do not establish transactional publication by independent file writers",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.seconds <= 90:
        parser.error("Require bounded duration2..90seconds; default60seconds")
    report = asyncio.run(run(args.seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"PASS {report['total_invocations']} mixed invocations; {args.output}"
    )
