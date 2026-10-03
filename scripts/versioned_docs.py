"""Build immutable tag documentation with mike and preserve legacy entry URLs."""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def extract_revision(revision, destination):
    archive = subprocess.check_output(["git", "archive", revision])
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(destination, filter="data")


def backfill_initial_release(branch):
    versions = json.loads(command("mike", "list", "--json", "--branch", branch))
    if any(item["version"] == "1.0.0" for item in versions):
        return
    with tempfile.TemporaryDirectory(
        prefix="fastfence-docs-history-"
    ) as directory:
        root = Path(directory)
        extract_revision("v1.0.0", root)
        config_file = root / "mkdocs.yml"
        config = yaml.safe_load(config_file.read_text())
        config.setdefault("extra", {})["version"] = {"provider": "mike"}
        config_file.write_text(yaml.safe_dump(config, sort_keys=False))
        subprocess.run(
            [
                "mike",
                "deploy",
                "--branch",
                branch,
                "--config-file",
                str(config_file),
                "--prop-set-string",
                "git_tag=v1.0.0",
                "1.0.0",
            ],
            check=True,
        )


def legacy_entrypoints(output, version):
    current = output / version
    # Keep public machine-readable/download URLs working after introducing versions.
    for name in ("llms.txt", "llms-full.txt", "CNAME"):
        if (current / name).is_file():
            shutil.copyfile(current / name, output / name)
    shutil.copytree(
        current / "downloads", output / "downloads", dirs_exist_ok=True
    )
    for page in current.rglob("index.html"):
        relative = page.relative_to(current)
        if relative == Path("index.html"):
            continue
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        url = "/latest/" + relative.parent.as_posix() + "/"
        target.write_text(
            '<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={url}">'
            f'<link rel="canonical" href="{url}"></head>'
            f'<body><a href="{url}">FastFence documentation</a></body></html>\n'
        )


def build(tag, output, *, branch="gh-pages", initial_archive=True):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError(
            "Documentation requires an exact stable vMAJOR.MINOR.PATCH tag"
        )
    if command("git", "rev-parse", "HEAD") != command(
        "git", "rev-parse", tag + "^{commit}"
    ):
        raise ValueError("Documentation source must match the release tag")
    version = tag[1:]
    if initial_archive and version != "1.0.0":
        backfill_initial_release(branch)
    existing = json.loads(command("mike", "list", "--json", "--branch", branch))
    stable = [
        item["version"]
        for item in existing
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", item["version"])
    ]
    latest = max(
        [version, *stable], key=lambda item: tuple(map(int, item.split(".")))
    )
    aliases = ["latest"] if version == latest else []
    subprocess.run(
        [
            "mike",
            "deploy",
            "--branch",
            branch,
            "--update-aliases",
            "--alias-type",
            "copy",
            "--prop-set-string",
            f"git_tag={tag}",
            version,
            *aliases,
        ],
        check=True,
    )
    subprocess.run(
        ["mike", "set-default", "--branch", branch, "latest"], check=True
    )
    if output.exists():
        raise ValueError("Choose an empty documentation artifact destination")
    output.mkdir(parents=True)
    extract_revision(branch, output)
    legacy_entrypoints(output, latest)
    versions = json.loads((output / "versions.json").read_text())
    assert any(
        item["version"] == latest and "latest" in item["aliases"]
        for item in versions
    )
    print(f"Versioned documentation ready for {tag}: {output}")


def build_dev(sha, output, *, branch="gh-pages"):
    """Publish verified main source without moving stable aliases or entry URLs."""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError(
            "Development documentation requires an exact commit SHA"
        )
    if command("git", "rev-parse", "HEAD") != sha:
        raise ValueError(
            "Development source must match the verified commit SHA"
        )
    if output.exists():
        raise ValueError("Choose an empty documentation artifact destination")
    versions = json.loads(command("mike", "list", "--json", "--branch", branch))
    stable = [
        item["version"]
        for item in versions
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", item["version"])
    ]
    if not stable:
        # v1.0.0 is an already published and independently verified package.
        # Bootstrap only this known release, never the unreleased working version.
        backfill_initial_release(branch)
        subprocess.run(
            [
                "mike",
                "alias",
                "--branch",
                branch,
                "--alias-type",
                "copy",
                "1.0.0",
                "latest",
            ],
            check=True,
        )
        subprocess.run(
            ["mike", "set-default", "--branch", branch, "latest"],
            check=True,
        )
        stable = ["1.0.0"]
    latest = max(stable, key=lambda item: tuple(map(int, item.split("."))))
    previous = next(
        (item for item in versions if item["version"] == "dev"), None
    )
    previous_sha = (previous or {}).get("properties", {}).get("git_sha")
    if previous_sha and previous_sha != sha:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", previous_sha, sha],
            check=False,
        )
        if result.returncode:
            raise ValueError(
                "Refusing an older or divergent development source"
            )
    subprocess.run(
        [
            "mike",
            "deploy",
            "--branch",
            branch,
            "--title",
            "dev (unreleased)",
            "--prop-set-string",
            f"git_sha={sha}",
            "dev",
        ],
        env={**os.environ, "FASTFENCE_DOCS_SOURCE_SHA": sha},
        check=True,
    )
    output.mkdir(parents=True)
    extract_revision(branch, output)
    legacy_entrypoints(output, latest)
    published = json.loads((output / "versions.json").read_text())
    assert any(
        item["version"] == latest and "latest" in item["aliases"]
        for item in published
    )
    print(f"Development documentation ready for {sha}: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tag", help="Stable tag or exact verified SHA with --dev"
    )
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("site-versioned"))
    parser.add_argument("--branch", default="gh-pages")
    args = parser.parse_args()
    builder = build_dev if args.dev else build
    builder(args.tag, args.output.resolve(), branch=args.branch)
