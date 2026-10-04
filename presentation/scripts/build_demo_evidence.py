"""Render factual video report frames from the reviewed evidence map.

Requires Pillow. Set FASTFENCE_PRESENTATION_FONT to a Helvetica-compatible font
when the default macOS font is unavailable. This draws editorial summaries,
never simulated product UI or terminal output.
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "presentation/output"
FONT = os.environ.get(
    "FASTFENCE_PRESENTATION_FONT", "/System/Library/Fonts/Helvetica.ttc"
)
BG = "#092524"
FG = "#F6F7F2"
MUTED = "#B9CBC7"
ACCENT = "#CCF578"


def font(size):
    return ImageFont.truetype(FONT, size)


def text(draw, xy, value, size=32, fill=FG):
    draw.text(xy, value, font=font(size), fill=fill, spacing=11)


def frame():
    image = Image.new("RGB", (1920, 945), BG)
    return image, ImageDraw.Draw(image)


def main():
    im, d = frame()
    text(d, (120, 68), "Measured behavior, with scope", 64)
    rows = [
        (
            195,
            "0.248 ms",
            "Historical deterministic p95",
            "Public 1.0.2 • Apple M3 Pro • 2,000 calls + 100 warmups\nConcurrency 1 • direct Python • no HTTP or LLM inference",
        ),
        (
            390,
            "1,000 / 1,000",
            "Controlled scheduling check",
            "FastFence 1.0.7 • 8 active, 992 waiting\nSynthetic provider • no model inference",
        ),
        (
            585,
            "12 / 12",
            "Real-model integration check",
            "Candidate wheel 1.0.7 • 2 admitted at once\n24 Laya assessments + actual Qwen responses",
        ),
    ]
    for y, value, label, scope in rows:
        text(d, (120, y), value, 68, ACCENT)
        text(d, (700, y + 3), label, 38)
        text(d, (700, y + 58), scope, 30, MUTED)
    text(
        d,
        (120, 807),
        "Separate workloads. No production latency or throughput guarantee.",
        30,
        MUTED,
    )
    text(
        d,
        (120, 867),
        "Sources: installed-package-1.0.2-comparison.json; request-queue-1.0.7.json",
        24,
        MUTED,
    )
    im.save(OUT / "benchmark-demo.png")
    im, d = frame()
    text(d, (120, 68), "What the demo demonstrates", 64)
    rows = [
        ("Guardrails", "Request blocks and document redaction"),
        (
            "Architecture and efficiency",
            "Live policy changes. Local checks first.",
        ),
        (
            "Security reporting",
            "Decision reason, policy version, upstream status",
        ),
        (
            "Self-testing",
            "Allowed and blocked examples reviewed before activation",
        ),
        (
            "Practical integration",
            "OpenAI client using the protected /v1 endpoint",
        ),
    ]
    for i, (label, evidence) in enumerate(rows):
        y = 215 + i * 112
        text(d, (120, y), label, 38, ACCENT)
        text(d, (650, y + 4), evidence, 32)
    text(
        d,
        (120, 807),
        "Official criterion categories. Evidence map, not a jury score.",
        30,
        MUTED,
    )
    text(
        d,
        (120, 867),
        "Source: AI Control Layer challenge criteria and competition rules",
        24,
        MUTED,
    )
    im.save(OUT / "requirements-demo.png")


if __name__ == "__main__":
    main()
