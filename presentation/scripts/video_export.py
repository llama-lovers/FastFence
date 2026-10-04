"""Export continuous browser video with explanatory caption images and SRT.

PNG overlays avoid depending on an ffmpeg build with libass or drawtext.
"""

import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02},{milliseconds:03}"


def export_video(raw, target, captions, duration, trim):
    subtitles = target.parent / "demo-captions.srt"
    lines = []
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        str(trim),
        "-i",
        str(raw),
    ]
    filters = ["[0:v]pad=iw:ih+90:0:0:color=0x111827[v0]"]
    fonts = [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font_path = next((path for path in fonts if path.exists()), None)
    font = (
        ImageFont.truetype(str(font_path), 23)
        if font_path
        else ImageFont.load_default(size=23)
    )
    with tempfile.TemporaryDirectory(
        prefix="fastfence-caption-images-"
    ) as folder:
        for index, (start, message) in enumerate(captions):
            end = (
                captions[index + 1][0]
                if index + 1 < len(captions)
                else duration
            )
            lines.append(
                f"{index + 1}\n{timestamp(start)} --> {timestamp(end)}\n{message}\n"
            )
            strip = Image.new("RGB", (1600, 90), "#111827")
            draw = ImageDraw.Draw(strip)
            wrapped = "\n".join(textwrap.wrap(message, width=115))
            draw.multiline_text(
                (800, 45),
                wrapped,
                font=font,
                fill="#ffffff",
                anchor="mm",
                align="center",
                spacing=5,
            )
            path = Path(folder) / f"caption-{index}.png"
            strip.save(path)
            command.extend(["-loop", "1", "-i", str(path)])
            filters.append(
                f"[v{index}][{index + 1}:v]overlay=0:900:enable='gte(t,{start})*lt(t,{end})'[v{index + 1}]"
            )
        subtitles.write_text("\n".join(lines))
        command.extend(
            [
                "-filter_complex_threads",
                "1",
                "-filter_complex",
                ";".join(filters),
                "-map",
                f"[v{len(captions)}]",
                "-t",
                str(duration),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
        subprocess.run(command, check=True)
