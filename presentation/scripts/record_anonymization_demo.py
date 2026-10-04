"""Record real RSA reversible anonymization through isolated public FastFence.

Fresh RSA-3072 keys plus an issuer keyring, actual HTTP and deterministic echo.
No model inference. No full encrypted tokens, credentials or keys in artifacts.
"""

import argparse
import importlib.metadata
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from .acp_demo_services import start_server
    from .anonymization_demo_setup import EchoTools, build
else:
    from acp_demo_services import start_server
    from anonymization_demo_setup import EchoTools, build

ORIGINAL = "Anna Kowalska"


def flow(base, tokens, tools):
    import httpx

    with httpx.Client(base_url=base, trust_env=False, timeout=30) as client:
        agent = {"Authorization": "Bearer " + tokens["agent"]}
        admin = {"Authorization": "Bearer " + tokens["admin"]}

        def invoke(restore):
            response = client.post(
                "/api/invoke",
                headers=agent,
                json={
                    "tool": "demo.echo",
                    "arguments": {"text": ORIGINAL},
                    "restore_originals": restore,
                },
            )
            response.raise_for_status()
            return response.json()

        initial = client.get("/api/admin/status", headers=admin).json()
        protected = invoke(False)
        assert protected["anonymized"] and not protected["restored"]
        token = protected["output"]["text"]
        assert token.startswith("[FFR2.") and ORIGINAL not in token
        assert tools.received == [token]
        restored = invoke(True)
        assert restored["restored"] and restored["output"]["text"] == ORIGINAL
        assert len(tools.received) == 2
        assert all(
            text.startswith("[FFR2.") and ORIGINAL not in text
            for text in tools.received
        )
        stable = (
            tools.received[0].split(".")[4] == tools.received[1].split(".")[4]
        )
        randomized = tools.received[0] != tools.received[1]
        assert stable and randomized
        policy = initial["policy"]
        policy["version"] = 2
        policy["anonymization"]["rules"][0]["allow_restore"] = False
        response = client.put("/api/admin/policy", headers=admin, json=policy)
        response.raise_for_status()
        denied = invoke(True)
        assert denied["reason"] == "anonymization_restore_denied"
        assert not denied["restored"] and ORIGINAL not in json.dumps(denied)
        assert all(ORIGINAL not in text for text in tools.received)
        audit = client.get("/api/admin/audit.jsonl", headers=admin).text
        assert ORIGINAL not in audit and all(
            text not in audit for text in tools.received
        )
        final = client.get("/api/admin/status", headers=admin).json()
        assert (
            final["runtime"]["instance_id"] == initial["runtime"]["instance_id"]
        )
        assert final["metrics"]["semantic_calls"] == 0
    return {
        "package_version": importlib.metadata.version("fastfence"),
        "installed_site_packages_verified": True,
        "public_package_cached_offline": True,
        "same_gateway_instance": True,
        "cryptography": "RSA-3072 OAEP-SHA256 wraps AES-256-GCM, with issuer authentication",
        "token_format": "FFR2",
        "fresh_recipient_key_pair": True,
        "fresh_issuer_keyring": True,
        "both_recipient_keys_loaded_by_gateway": True,
        "synthetic_original": ORIGINAL,
        "upstream": "Explicit deterministic echo ToolsPort",
        "model_inference": False,
        "semantic_provider": "disabled",
        "semantic_calls": 0,
        "restore_off": {
            "decision": protected["decision"],
            "anonymized": protected["anonymized"],
            "restored": False,
            "upstream_executed": protected["upstream_executed"],
            "upstream_original_absent": True,
            "delivered_preview": token[:12] + "... [abbreviated]",
            "preview_is_not_restorable_token": True,
            "echo_invocations": 1,
        },
        "restore_on": {
            "decision": restored["decision"],
            "anonymized": restored["anonymized"],
            "restored": True,
            "upstream_executed": restored["upstream_executed"],
            "upstream_original_absent": True,
            "delivered_text": restored["output"]["text"],
            "echo_invocations": 2,
        },
        "permission_denied": {
            "policy_version": 2,
            "restore_originals": True,
            "allow_restore": False,
            "decision": denied["decision"],
            "reason": denied["reason"],
            "restored": False,
            "upstream_executed": denied["upstream_executed"],
            "echo_invocations": len(tools.received),
        },
        "stable_scoped_identifier_for_repeated_original": stable,
        "randomized_encrypted_tokens": randomized,
        "audit_excludes_original_and_full_tokens": True,
        "full_tokens_and_keys_excluded_from_artifacts": True,
        "scope": "Actual HTTP plus real crypto and deterministic echo, not model output preservation. Self-contained tokens require no conversation mapping database; full gateway holds both RSA keys and issuer keyring. Restoration remains subject to output controls.",
    }


def worker(args):
    import fastfence

    assert importlib.metadata.version("fastfence") == "1.0.7"
    assert "site-packages" in str(Path(fastfence.__file__).resolve())
    root = Path.cwd() / "operator"
    root.mkdir()
    tools, servers = EchoTools(), []
    tokens = {name: secrets.token_urlsafe(32) for name in ("agent", "admin")}
    try:
        base = start_server(build(root, tokens, tools), servers)
        report = flow(base, tokens, tools)
    finally:
        for server, thread, sock in reversed(servers):
            server.should_exit = True
            thread.join(timeout=15)
            sock.close()
            if thread.is_alive():
                raise RuntimeError("Isolated gateway did not shut down")
    report["owned_service_stopped"] = True
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_name("anonymization-demo-transcript.txt").write_text(
        "Actual reversible anonymization | public FastFence 1.0.7\n"
        "Fresh RSA-3072 key pair + issuer keyring. Deterministic echo, no LLM.\n\n"
        f"Synthetic input: {ORIGINAL}\n"
        f"restore_originals=false -> {report['restore_off']['delivered_preview']}\n"
        "upstream original absent | anonymized=true | restored=false\n"
        f"restore_originals=true, allow_restore=true -> {ORIGINAL}\n"
        "upstream original absent | restored=true | echo calls=2\n"
        "Same scoped identifier, randomized ciphertext on repeated input.\n"
        "Policy v2 allow_restore=false + request restore=true -> anonymization_restore_denied\n"
        f"upstream_executed={str(report['permission_denied']['upstream_executed']).lower()} | echo calls={len(tools.received)}\n"
        "Full gateway holds both recipient keys. No keys or full tokens exported.\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    log = root / "state/private/anonymization-demo-raw.log"
    env = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "HOME", "LANG", "TMPDIR", "UV_CACHE_DIR"}
    }
    with tempfile.TemporaryDirectory(prefix="fastfence-privacy-demo-") as temp:
        entry = Path(temp) / "record_anonymization_demo.py"
        shutil.copyfile(__file__, entry)
        for name in ("acp_demo_services.py", "anonymization_demo_setup.py"):
            shutil.copyfile(Path(__file__).with_name(name), Path(temp) / name)
        shutil.copyfile(
            root / "examples/docs/asymmetric_keys.py",
            Path(temp) / "asymmetric_keys.py",
        )
        with log.open("w") as stream:
            result = subprocess.run(
                [
                    "uv",
                    "--offline",
                    "--no-config",
                    "run",
                    "--no-project",
                    "--python",
                    "3.12",
                    "--with",
                    "fastfence==1.0.7",
                    "python",
                    str(entry),
                    "--worker",
                    "--output",
                    str(args.output),
                ],
                cwd=temp,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
        if result.returncode:
            raise SystemExit("Privacy demo failed; inspect private log")
    sys.stdout.write(
        "Verified real reversible privacy; owned gateway stopped and fresh keys removed.\n"
    )


if __name__ == "__main__":
    main()
