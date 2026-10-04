"""Render exact recorded SDK evidence, never simulate a new execution."""

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "presentation/output"
BUILD = ROOT / "state/private/demo-v3-integration"
FONT = Path("/System/Library/Fonts/Menlo.ttc")
if not FONT.exists():
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


def text(draw, point, value, size=32, color="#F4F8F7"):
    draw.multiline_text(
        point,
        value,
        font=ImageFont.truetype(str(FONT), size),
        fill=color,
        spacing=17,
    )


def canvas(title):
    image = Image.new("RGB", (1920, 945), "#0B2029")
    draw = ImageDraw.Draw(image)
    text(draw, (80, 55), title, 36, "#4EE0BE")
    draw.line((80, 125, 1840, 125), fill="#35505A", width=2)
    return image, draw


def encode(image, name, duration):
    path = BUILD / (name + ".png")
    video = BUILD / (name + ".mp4")
    image.save(path)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(path),
            "-t",
            str(duration),
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "pad=1920:946:0:0",
            "-crf",
            "18",
            str(video),
        ],
        check=True,
    )
    return video


def concat(parts, name):
    path = BUILD / (name + ".txt")
    path.write_text("\n".join(f"file '{part}'" for part in parts))
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
            str(path),
            "-c",
            "copy",
            str(OUT / (name + ".mp4")),
        ],
        check=True,
    )


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    evidence = json.loads((OUT / "integration-demo-evidence.json").read_text())
    assert (
        evidence["same_gateway_instance"] and not evidence["synthetic_upstream"]
    )
    assert evidence["allowed"]["http_status"] == 200
    assert evidence["blocked"]["http_status"] == 403
    image, draw = canvas("Integration path")
    for x, label in [
        (630, "App / SDK"),
        (1060, "FastFence /v1"),
        (1490, "Qwen"),
    ]:
        draw.rounded_rectangle(
            (x, 40, x + 330, 108), radius=10, outline="#4EE0BE", width=2
        )
        text(draw, (x + 20, 58), label, 29)
    text(draw, (980, 58), "→", 30, "#4EE0BE")
    text(draw, (1410, 58), "→", 30, "#4EE0BE")
    lines = [
        "from openai import OpenAI",
        "import os",
        "",
        "client = OpenAI(",
        "    base_url=os.environ['FASTFENCE_URL'] + '/v1',",
        "    api_key=os.environ['FASTFENCE_AGENT_TOKEN'],",
        "    max_retries=0,",
        ")",
        "",
        "response = client.chat.completions.create(",
        "    model='qwen3:0.6b',",
        "    messages=[{'role': 'user', 'content': 'Hello'}],",
        "    max_tokens=256, temperature=0, stream=False,",
        ")",
    ]
    text(draw, (115, 170), "\n".join(lines), 31)
    text(
        draw,
        (117, 865),
        "Standard SDK call · credentials stay in environment variables",
        24,
        "#A9C3C9",
    )
    code = encode(image, "sdk-code", 6)
    image, draw = canvas(
        "Recorded SDK integration result · public FastFence 1.0.7"
    )
    text(draw, (115, 185), "OpenAI SDK 3.24.0  /  actual local Qwen + Laya", 33)
    selected = {
        key: evidence["allowed"][key]
        for key in (
            "http_status",
            "policy_version",
            "decision",
            "upstream_executed",
            "semantic_input_status",
            "semantic_output_status",
        )
    }
    text(draw, (115, 290), json.dumps(selected, indent=2), 40, "#4EE0BE")
    text(
        draw,
        (115, 825),
        "Recorded API fields · separate isolated session from the UI footage",
        25,
        "#A9C3C9",
    )
    result = encode(image, "sdk-allowed", 4)
    concat([code, result], "integration-demo")
    parts = []
    for state, title, color in [
        ("allowed", "BEFORE: actual model executed", "#4EE0BE"),
        ("blocked", "AFTER: same request stopped before model", "#FFA886"),
    ]:
        image, draw = canvas("Recorded API results · same gateway instance")
        text(draw, (110, 178), title, 38, color)
        fields = [
            "http_status",
            "policy_version",
            "decision",
            "upstream_executed",
        ]
        if state == "blocked":
            fields += ["reason", "budget_units"]
        selected = {key: evidence[state][key] for key in fields}
        text(draw, (115, 285), json.dumps(selected, indent=2), 44, color)
        text(
            draw,
            (115, 790),
            "Identical SDK payload: Hello  |  policy v1 → v2  |  no restart",
            29,
        )
        text(
            draw,
            (115, 850),
            "Actual recorded response fields; replayed for readability",
            24,
            "#A9C3C9",
        )
        parts.append(encode(image, "backend-" + state, 5))
    concat(parts, "backend-demo")


if __name__ == "__main__":
    main()
