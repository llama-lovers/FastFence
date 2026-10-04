"""Replace the final V4 evidence card with the official five scoring categories.

Preserves the original V4 and copies its original instrumental audio unchanged.
No inference or recording is performed.
"""

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "presentation/output"
FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
if not FONT.exists():
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def main():
    image = Image.new("RGB", (1920, 945), "#092927")
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=34, color="#F3F7F6", bold=False):
        draw.text(
            (x, y),
            value,
            font=ImageFont.truetype(str(BOLD if bold else FONT), size),
            fill=color,
        )

    text(
        110,
        45,
        "Five judging categories. Demonstrated evidence.",
        58,
        bold=True,
    )
    rows = [
        (
            "30%",
            "Guardrails",
            "Local blocks, Laya review, OCR privacy, authorized restoration",
        ),
        (
            "20%",
            "Architecture & performance",
            "Hot policy changes, bounded queues, scoped benchmarks",
        ),
        (
            "20%",
            "Security reporting",
            "Decision reason, policy version, execution status, audit export",
        ),
        (
            "15%",
            "Self-testing",
            "Allowed and blocked cases reviewed before activation",
        ),
        (
            "15%",
            "Practical integration",
            "Real OpenAI SDK, MCP tool and ACP agent calls",
        ),
    ]
    for index, (weight, title, evidence) in enumerate(rows):
        y = 187 + index * 123
        text(110, y, weight, 44, "#D1FF76", True)
        text(278, y + 4, title, 35, bold=True)
        text(805, y + 9, evidence, 29)
        draw.line((110, y + 91, 1810, y + 91), fill="#295047", width=1)
    text(
        110,
        835,
        "Official category weights. Evidence mapping; no self-awarded scores.",
        30,
        "#B5CACA",
    )
    card = OUT / "submission-requirements.png"
    image.save(card)
    target = OUT / "fastfence-submission.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(OUT / "fastfence-demo-v4.mp4"),
            "-loop",
            "1",
            "-i",
            str(card),
            "-filter_complex_threads",
            "1",
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:enable='gte(t,172)*lt(t,177)'[v]",
            "-map",
            "[v]",
            "-map",
            "0:a:0",
            "-t",
            "180",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(target),
        ],
        check=True,
    )
    timeline = json.loads((OUT / "demo-v4-timeline.json").read_text())
    timeline["submission_edit"] = {
        "start_seconds": 172,
        "end_seconds": 177,
        "card": card.name,
        "weights_percent": [30, 20, 20, 15, 15],
        "original_preserved": "fastfence-demo-v4.mp4",
        "audio_unchanged": True,
    }
    (OUT / "submission-timeline.json").write_text(
        json.dumps(timeline, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
