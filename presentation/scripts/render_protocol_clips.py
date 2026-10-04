"""Render reviewed recorded protocol fields; performs no MCP/ACP calls.

The evidence recordings must exist before use. Results are presented as replayed
records, never as newly executing terminals. Protocol JSON keys are preserved.
"""

import json
from pathlib import Path

import render_integration_clips as media

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "presentation/output"


def card(title, lines, color="#F4F8F7", footer=None):
    image, draw = media.canvas(title)
    media.text(draw, (100, 170), "\n".join(lines), 32, color)
    if footer:
        media.text(draw, (100, 865), footer, 24, "#A9C3C9")
    return image


def render(protocol, specification):
    media.BUILD = ROOT / "state/private" / ("demo-v4-" + protocol)
    media.BUILD.mkdir(parents=True, exist_ok=True)
    evidence_file = OUT / specification["evidence_file"]
    evidence = json.loads(evidence_file.read_text())
    # Exact selected fields and code are validated against each recorded run by
    # the protocol owner before this explicit rendering manifest is supplied.
    assert evidence, "Recorded evidence is required"
    parts = []
    for index, section in enumerate(specification["sections"]):
        image = card(
            section["title"],
            section["lines"],
            section.get("color", "#F4F8F7"),
            section.get("footer"),
        )
        parts.append(
            media.encode(
                image, protocol + f"-{index}", section["duration_seconds"]
            )
        )
    assert sum(
        section["duration_seconds"] for section in specification["sections"]
    ) == (20 if protocol == "anonymization" else 16)
    media.concat(parts, protocol + "-demo")


def main():
    manifest = json.loads((OUT / "protocol-clips-manifest.json").read_text())
    for protocol in ("mcp", "acp", "anonymization"):
        render(protocol, manifest[protocol])


if __name__ == "__main__":
    main()
