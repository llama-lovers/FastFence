"""Append real OCR and model UI footage from an explicitly isolated gateway.

Uses the installed product over HTTP; never intercepts API responses. Requires
Playwright, Pillow and ffmpeg. The source preview must render the supplied PDF.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ocr_capture import capture
from video_export import export_video, timestamp


def probe_duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def record(args):
    args.output = args.output.resolve()
    args.assets = args.assets.resolve()
    args.assets.mkdir(parents=True, exist_ok=True)
    archive = Path("state/private/fastfence-demo-before-ocr-90s.mp4").resolve()
    if archive.exists():
        if args.output.read_bytes() != archive.read_bytes():
            raise ValueError(
                "Demo already changed after archive; avoid appending OCR twice"
            )
    else:
        shutil.copy2(args.output, archive)
    original_srt = (args.output.parent / "demo-captions.srt").read_text()
    base_duration = probe_duration(archive)
    with tempfile.TemporaryDirectory(
        prefix="fastfence-ocr-recording-"
    ) as directory:
        folder = Path(directory)
        raw, captions, duration, trim, report = capture(args, folder)
        ui = folder / "ocr-ui.mp4"
        export_video(raw, ui, captions, duration, trim)
        preview_dir = folder / "preview"
        preview_dir.mkdir()
        source = preview_dir / "source.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(args.source_preview),
                "-t",
                "6",
                "-vf",
                "scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=white",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(source),
            ],
            check=True,
        )
        preview = preview_dir / "preview.mp4"
        preview_caption = "Source PDF preview: two pages of synthetic contact data. Original emails are visible here."
        export_video(source, preview, [(0, preview_caption)], 6, 0)
        concat = folder / "concat.txt"
        concat.write_text(
            "\n".join(
                "file '" + str(path) + "'" for path in (archive, preview, ui)
            )
            + "\n"
        )
        subprocess.run(
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
                str(args.output),
            ],
            check=True,
        )
    combined_duration = probe_duration(args.output)
    new_captions = [(base_duration, preview_caption)] + [
        (base_duration + 6 + start, message) for start, message in captions
    ]
    blocks = [original_srt.rstrip()]
    for index, (start, message) in enumerate(new_captions, 13):
        relative = index - 13
        end = (
            new_captions[relative + 1][0]
            if relative + 1 < len(new_captions)
            else combined_duration
        )
        blocks.append(
            f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{message}"
        )
    (args.output.parent / "demo-captions.srt").write_text(
        "\n\n".join(blocks) + "\n"
    )
    report["appendix_duration_seconds"] = round(
        combined_duration - base_duration, 3
    )
    (args.output.parent / "ocr-demo-evidence.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    evidence_path = args.output.parent / "demo-evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["base_policy_demo_scope"] = (
        "same_instance and top-level semantic_calls describe the original policy segment only; OCR is a separate isolated session."
    )
    evidence.update(
        duration_seconds=round(combined_duration, 3),
        policy_demo_duration_seconds=base_duration,
        ocr=report,
    )
    evidence["edits"] = (
        "Original 90-second policy demo followed by a six-second source PDF preview and separate continuous real OCR/UI recording. Credential connection and idle tails omitted; actual inference waits retained. Captions added."
    )
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    sys.stdout.write(json.dumps(report) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--source-preview", type=Path, required=True)
    parser.add_argument("--expected-redacted", action="append", required=True)
    parser.add_argument("--agent-key", default="agent")
    parser.add_argument("--admin-key", default="admin")
    parser.add_argument("--model", default="qwen3:0.6b")
    parser.add_argument(
        "--assets", type=Path, default=Path("presentation/assets")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("presentation/output/fastfence-demo.mp4"),
    )
    parser.add_argument(
        "--isolated-demo-confirmed", action="store_true", required=True
    )
    record(parser.parse_args())


if __name__ == "__main__":
    main()
