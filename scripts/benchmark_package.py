"""Run the existing core benchmark against an isolated installed distribution.

Run from a checkout or the published benchmark bundle; only explicit benchmark
fixtures are staged. No FastFence source code is copied or added to PYTHONPATH.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

BUNDLE_FILES = (
    "evaluation/benchmark_gateway.py",
    "evaluation/business_fixture.py",
    "examples/business_tools/tools.py",
    "examples/business_tools/credentials.py",
    "examples/business_tools/policy.yaml",
    "config/signatures.json",
)


def clean_environment():
    allowed = {"PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT", "UV_CACHE_DIR"}
    environment = {
        key: value for key, value in os.environ.items() if key in allowed
    }
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    return environment


def stage_bundle(source, destination):
    checksums = {}
    for name in BUNDLE_FILES:
        original = (source / name).resolve()
        if (
            not original.is_relative_to(source.resolve())
            or not original.is_file()
        ):
            raise ValueError(
                "Benchmark bundle is incomplete or contains an external path"
            )
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        checksums[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return checksums


def execute(command, root, environment, timeout=900):
    subprocess.run(
        command, cwd=root, env=environment, check=True, timeout=timeout
    )


def validate(args):
    if not 1 <= args.samples <= 250000 or not 0 <= args.warmup <= 10000:
        raise ValueError("Require samples1..250000 and warmup0..10000")
    if not args.concurrency or any(
        not 1 <= count <= 100 for count in args.concurrency
    ):
        raise ValueError("Concurrency must be1..100")
    if args.semantic and args.concurrency != [1]:
        raise ValueError("Actual Laya mode requires --concurrency 1")
    if args.pypi_version and not re.fullmatch(
        r"\d+\.\d+\.\d+", args.pypi_version
    ):
        raise ValueError("Use an exact stable public package version")
    if args.wheel and (not args.wheel.is_file() or args.wheel.suffix != ".whl"):
        raise ValueError("A built wheel is required")


def benchmark(args):
    validate(args)
    source = Path(__file__).resolve().parents[1]
    environment = clean_environment()
    output = args.output.resolve()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(
        prefix="fastfence-package-benchmark-"
    ) as temporary:
        root = Path(temporary)
        if root.is_relative_to(source):
            raise ValueError(
                "Benchmark temporary workspace must be outside its source bundle"
            )
        checksums = stage_bundle(source, root)
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
        executable = root / "venv/bin/fastfence"
        distribution = (
            f"fastfence=={args.pypi_version}"
            if args.pypi_version
            else str(args.wheel.resolve())
        )
        execute(
            [
                "uv",
                "--native-tls",
                "--no-config",
                "pip",
                "install",
                "--refresh-package",
                "fastfence",
                "--python",
                str(python),
                "--default-index",
                "https://pypi.org/simple",
                distribution,
            ],
            root,
            environment,
        )
        # Validate before init or benchmark; no .env or checkout settings inherited.
        execute(
            [
                str(python),
                "-c",
                """import importlib.metadata,json,pathlib,sys,zipfile
import fastfence
package=pathlib.Path(fastfence.__file__).resolve().parent
assert package.is_relative_to(pathlib.Path(sys.prefix).resolve()) and 'site-packages' in package.parts
assert not any(pathlib.Path(p or '.').resolve().is_relative_to(pathlib.Path(sys.argv[1])) for p in sys.path)
version=importlib.metadata.version('fastfence')
if sys.argv[2]: assert version==sys.argv[2]
if sys.argv[3]:
 with zipfile.ZipFile(sys.argv[3]) as wheel:
  for name in wheel.namelist():
   if name.startswith('fastfence/') and not name.endswith('/'):
    assert (package.parent/name).read_bytes()==wheel.read(name)
pathlib.Path('installed.json').write_text(json.dumps({'version':version,'installed_distribution':True,'checkout_imports_excluded':True}))
""",
                str(source),
                args.pypi_version or "",
                str(args.wheel.resolve()) if args.wheel else "",
            ],
            root,
            environment,
        )
        if args.semantic:
            # Explicit init provisions Laya and configured Qwen; no no-argument OCR startup.
            execute([str(executable), "init"], root, environment, timeout=1800)
        command = [
            str(python),
            str(root / "evaluation/benchmark_gateway.py"),
            "--samples",
            str(args.samples),
            "--warmup",
            str(args.warmup),
            "--concurrency",
            *map(str, args.concurrency),
            "--upstream-modes",
            "zero_wait_fixture",
            "--forbidden-root",
            str(source),
            "--output",
            str(root / "report.json"),
        ]
        if args.semantic:
            command.append("--semantic")
        else:
            command.append("--include-baseline")
        execute(
            command, root, environment, timeout=3600 if args.semantic else 900
        )
        report = json.loads((root / "report.json").read_text())
        installed = json.loads((root / "installed.json").read_text())
        if report["package"] != installed:
            raise ValueError(
                "Benchmark import provenance changed during execution"
            )
        report["installation"] = {
            "source": "public_pypi" if args.pypi_version else "local_wheel",
            "wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest()
            if args.wheel
            else None,
            "benchmark_bundle_sha256": checksums,
            "fresh_external_environment": True,
            "total_setup_and_benchmark_seconds": round(
                time.monotonic() - started, 3
            ),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Installed-package benchmark passed: {output}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pypi-version")
    source.add_argument("--wheel", type=Path)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 8])
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        benchmark(args)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
