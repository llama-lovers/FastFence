"""Measure preloaded token crypto, excluding key generation and gateway work."""

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import cryptography
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from fastfence.modules.anonymization.persistence.asymmetric import (
    AsymmetricEnvelope,
)
from fastfence.modules.anonymization.persistence.crypto import (
    StatelessTokenCodec,
)
from fastfence.shared.anonymization import (
    AnonymizationContext,
    AnonymizationRule,
)


def summary(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": round(statistics.mean(values), 6),
        "p95_ms": round(sorted(values)[int(0.95 * (len(values) - 1))], 6),
    }


def measure(codec: StatelessTokenCodec, size: int, count: int) -> dict:
    original = "x" * size
    rule = AnonymizationRule(id="value", operator="regex", value="x+")
    context = AnonymizationContext(tenant="synthetic", subject="benchmark")
    token = codec.issue(rule, original, context, "reversible")
    for _ in range(10):
        codec.verify(token, rule, context)
    issue, verify = [], []
    for _ in range(count):
        started = time.perf_counter_ns()
        token = codec.issue(rule, original, context, "reversible")
        issued = time.perf_counter_ns()
        assert codec.verify(token, rule, context).original == original
        verified = time.perf_counter_ns()
        issue.append((issued - started) / 1_000_000)
        verify.append((verified - issued) / 1_000_000)
    return {
        "original_bytes": size,
        "token_bytes": len(token.encode()),
        "samples": count,
        "issue": summary(issue),
        "verify": summary(verify),
        "issue_and_verify": summary(
            [a + b for a, b in zip(issue, verify, strict=True)]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    envelope = AsymmetricEnvelope(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    codecs = {
        name: StatelessTokenCodec(
            keyring={"benchmark": bytes(range(32))},
            current_key_id="benchmark",
            asymmetric_envelope=value,
        )
        for name, value in (("FFR1", None), ("FFR2", envelope))
    }
    result = {
        "scope": "Synthetic single-process preloaded token codec only; not gateway latency or throughput/SLA. No key generation, file/network I/O, model, OCR, matching or audit in timed operations.",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cryptography": cryptography.__version__,
        },
        "limits": {"max_value_bytes": 4096, "max_token_bytes": 8192},
        "results": {
            name: [measure(codec, size, 100) for size in (16, 4096)]
            for name, codec in codecs.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
