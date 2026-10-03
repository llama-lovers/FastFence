"""Generate a release changelog from the exact tag and its preceding release."""

import argparse
import html
import re
import subprocess
from pathlib import Path

REPOSITORY = "https://github.com/llama-lovers/FastFence"
TAG = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def notes(tag):
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError("Expected a stable vMAJOR.MINOR.PATCH tag")
    current = tuple(map(int, match.groups()))
    previous = []
    for candidate in git("tag", "--merged", tag).splitlines():
        parsed = TAG.fullmatch(candidate)
        if parsed and tuple(map(int, parsed.groups())) < current:
            previous.append((tuple(map(int, parsed.groups())), candidate))
    start = max(previous)[1] if previous else None
    revision = f"{start}..{tag}" if start else tag
    lines = [f"# FastFence {tag[1:]}", "", "## Changes", ""]
    for commit in git(
        "log", "--reverse", "--format=%H%x09%s", revision
    ).splitlines():
        sha, subject = commit.split("\t", 1)
        # Render contributor-controlled titles as plain text, not links or HTML.
        subject = html.escape(subject).replace("\\", "\\\\")
        for char in ("[", "]", "*", "_", "`", "~"):
            subject = subject.replace(char, "\\" + char)
        lines.append(f"- {subject} ([{sha[:7]}]({REPOSITORY}/commit/{sha}))")
    lines.extend(
        [
            "",
            f"[Install from PyPI](https://pypi.org/project/fastfence/{tag[1:]}/) · "
            f"[Versioned documentation](https://fastfence.dev/{tag[1:]}/)",
            "",
        ]
    )
    if start:
        lines.append(
            f"[Full comparison: {start} → {tag}]({REPOSITORY}/compare/{start}...{tag})"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(notes(args.tag))
