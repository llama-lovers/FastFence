"""Assemble a UI-first edited demonstration from genuine recorded evidence.

Uses real-time source excerpts, with omitted intervals disclosed on-screen.
External integration/backend evidence must exist before the final build.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "presentation/output"
BUILD = ROOT / "state/private/demo-v3"
SOURCE = OUT / "fastfence-demo.mp4"
FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
if not FONT.exists():
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def scene(name, duration, caption, source_start=None, asset=None, note=None):
    return {
        "id": name,
        "duration_seconds": duration,
        "caption": caption,
        "source_start_seconds": source_start,
        "asset": asset,
        "note": note or "Real capture · edited excerpts · playback 1x",
    }


SCENES = [
    scene(
        "intro",
        4,
        "FastFence: change protection without changing your agent.",
        6.1,
    ),
    scene(
        "integration",
        10,
        "One integration. Central rules around every request.",
        asset="integration-demo.mp4",
        note="Recorded SDK integration results · separate isolated session · exact response fields replayed",
    ),
    scene(
        "allowed",
        8,
        "Send a real request. Laya checks input and output; Qwen answers.",
        6.1,
    ),
    scene(
        "literal-rule",
        14,
        "Edit the rule. Test prohibited and permitted inputs. Activate explicitly.",
        18.232,
    ),
    scene(
        "blocked",
        7,
        "Same Hello. New policy. Blocked before the business model runs.",
        32.236,
    ),
    scene(
        "audit",
        6,
        "Inspect the reason, policy version and execution boundary.",
        39.334,
    ),
    scene(
        "laya-instruction",
        11,
        "Describe a rule in your words. Add expected block and permit cases.",
        45.45,
    ),
    scene(
        "laya-review",
        10,
        "Eight scoped cases pass. Confirm activation and save the regression suite.",
        65.629,
        note="Actual before/after semantic review · scoped cases · waiting interval omitted",
    ),
    scene(
        "pdf-source",
        6,
        "Two pages. Useful service information and synthetic contact details.",
        90,
        note="Actual source PDF · separate recorded OCR session",
    ),
    scene(
        "ocr-upload",
        12,
        "Upload the PDF. Local OCR extracts text; privacy rules redact matches.",
        100.25,
    ),
    scene(
        "ocr-markdown",
        8,
        "Two email redactions. Download protected Markdown or send it to the model.",
        113.927,
    ),
    scene(
        "ocr-answer",
        10,
        "Qwen summarizes protected text. Laya checks both directions.",
        134.847,
        note="Actual model result · intervening waiting omitted · original PDF not sent to business model",
    ),
    scene(
        "backend",
        10,
        "Verify the effect at the API boundary, not just in the dashboard.",
        asset="backend-demo.mp4",
        note="Recorded SDK integration results · policy v1 to v2 · actual fields replayed",
    ),
    scene(
        "benchmark",
        12,
        "Measure the protection layer with a reproducible package benchmark.",
        asset="benchmark-demo.png",
        note="Measured evidence · benchmark scope and environment shown",
    ),
    scene(
        "requirements",
        7,
        "Evidence shown: protection, dynamic policies, audit, tests and integration.",
        asset="requirements-demo.png",
        note="Challenge requirements mapped to demonstrated product behavior",
    ),
    scene(
        "close",
        5,
        "uv tool run fastfence     |     fastfence.dev",
        83.012,
        note="Requires uv and a running Ollama service · first run installs local components",
    ),
]


def run(command):
    subprocess.run(command, check=True)


def overlay(item, index):
    image = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 945, 1920, 1080), fill="#071C23")
    draw.rectangle(
        (0, 945, round(1920 * (index + 1) / len(SCENES)), 950), fill="#43DABD"
    )
    draw.text(
        (40, 973),
        item["caption"],
        font=ImageFont.truetype(str(BOLD), 30),
        fill="#F3F7F6",
    )
    draw.text(
        (40, 1027),
        item["note"],
        font=ImageFont.truetype(str(FONT), 19),
        fill="#A8C1C7",
    )
    path = BUILD / f"overlay-{index:02d}.png"
    image.save(path)
    return path


def render(index, item):
    asset = OUT / item["asset"] if item["asset"] else SOURCE
    if not asset.exists():
        return None
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    if asset.suffix == ".png":
        command += ["-loop", "1"]
    elif item["source_start_seconds"] is not None:
        command += ["-ss", str(item["source_start_seconds"])]
    command += ["-i", str(asset), "-loop", "1", "-i", str(overlay(item, index))]
    # Remove only the earlier editorial caption strip, retain the entire UI.
    crop = "crop=1600:900:0:0," if asset == SOURCE else ""
    filters = f"[0:v]{crop}scale=1920:945:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:0:color=0xE8EEF0[v];[v][1:v]overlay=0:0:shortest=1[out]"
    target = BUILD / f"scene-{index:02d}.mp4"
    command += [
        "-filter_complex_threads",
        "1",
        "-filter_complex",
        filters,
        "-map",
        "[out]",
        "-an",
        "-t",
        str(item["duration_seconds"]),
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(target),
    ]
    run(command)
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            str(item["duration_seconds"] / 2),
            "-i",
            str(target),
            "-frames:v",
            "1",
            str(BUILD / f"thumbnail-{index:02d}.jpg"),
        ]
    )
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--render-known",
        action="store_true",
        help="Render available genuine excerpts without exporting an incomplete film.",
    )
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    elapsed, timeline, paths, missing = 0, [], [], []
    for index, item in enumerate(SCENES):
        target = render(index, item)
        timeline.append(
            {
                **item,
                "start_seconds": elapsed,
                "end_seconds": elapsed + item["duration_seconds"],
            }
        )
        elapsed += item["duration_seconds"]
        if target:
            paths.append(target)
        else:
            missing.append(item["asset"])
        sys.stdout.write(
            f"{item['id']}: {'rendered' if target else 'waiting for actual evidence'}\n"
        )
        sys.stdout.flush()
    report = {
        "duration_seconds": elapsed,
        "resolution": "1920x1080",
        "edited": True,
        "playback_speed": 1,
        "voice": False,
        "scenes": timeline,
        "missing_assets": missing,
        "original_recording_preserved": True,
        "semantic_scope": "The financial example was already blocked by the base policy; this recording demonstrates review and activation, not a new causal verdict flip.",
    }
    (OUT / "demo-v3-timeline.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    if missing:
        if args.render_known:
            return
        raise SystemExit(
            "Missing genuine evidence assets: " + ", ".join(missing)
        )
    concat = BUILD / "concat.txt"
    concat.write_text("\n".join(f"file '{p}'" for p in paths))
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(BUILD / "fastfence-demo-v3-silent.mp4"),
        ]
    )

    track = OUT / "fastfence-soundtrack-v3.m4a"
    if not track.exists():
        raise SystemExit("Expected original 140-second soundtrack is missing")
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(BUILD / "fastfence-demo-v3-silent.mp4"),
            "-i",
            str(track),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-t",
            str(elapsed),
            "-movflags",
            "+faststart",
            str(OUT / "fastfence-demo-v3.mp4"),
        ]
    )
    report["audio"] = {
        "type": "original_instrumental",
        "source_track": track.name,
        "voice": False,
    }
    report["integration_evidence"] = "integration-demo-evidence.json"
    report["integration_presentation"] = (
        "Exact recorded response fields replayed; a separate session from original UI evidence. Code is the equivalent short SDK call with environment-backed credentials."
    )
    (OUT / "demo-v3-timeline.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
