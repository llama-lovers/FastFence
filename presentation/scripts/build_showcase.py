"""Compose an edited product film from unchanged recorded FastFence evidence.

No gateway calls. Cropping/scaling/layout preserve actual captured UI pixels;
editorial text is separate. Requires Pillow and ffmpeg on PATH.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "presentation/assets"
OUTPUT = ROOT / "presentation/output"
BUILD = ROOT / "state/private/showcase-v2"
SOURCE = OUTPUT / "fastfence-demo.mp4"
NAVY = "#071C23"
TEAL = "#4EE0BE"
WHITE = "#F3F7F6"
MUTED = "#A8C1C7"
FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
if not FONT.exists():
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def text(draw, xy, message, size=30, color=WHITE, bold=False, width=None):
    font = ImageFont.truetype(str(BOLD if bold else FONT), size)
    if width:
        message = "\n".join(textwrap.wrap(message, width=width))
    draw.multiline_text(xy, message, font=font, fill=color, spacing=14)


def run(command):
    subprocess.run(command, check=True)


def scene(
    identifier,
    duration,
    title,
    body,
    label,
    proof,
    source=None,
    crop=None,
    start=None,
    voice="",
):
    return dict(
        id=identifier,
        duration=duration,
        title=title,
        body=body,
        label=label,
        proof=proof,
        source=source,
        crop=crop,
        source_start=start,
        voice_pl=voice,
    )


SCENES = [
    scene(
        "hook",
        10,
        "Same request.\nNew policy.",
        "Change protection without changing your agent.",
        "HOT POLICY UPDATE",
        "Same running gateway. Genuine before / after results.",
        voice="Ten sam agent, to samo zapytanie. Zmieniamy politykę i zatrzymujemy żądanie przed modelem — bez restartu.",
    ),
    scene(
        "allowed",
        7,
        "Start with a\nreal request.",
        "Laya checks input and output. Qwen returns the answer.",
        "01 / CONTROL",
        "Public FastFence 1.0.7 · actual Laya + Qwen",
        "video",
        (920, 210, 640, 675),
        10.2,
        "FastFence stoi między aplikacją a modelem. Tutaj Laya sprawdza wejście i wyjście, a Qwen rzeczywiście odpowiada.",
    ),
    scene(
        "literal",
        10,
        "Test the rule.\nThen activate.",
        "A prohibited example. A permitted example. An explicit decision.",
        "01 / CONTROL",
        "Literal input rule · model scope · reviewed activation",
        "video",
        (450, 45, 700, 810),
        20.5,
        "Regułę najpierw sprawdzamy na przykładach. Widzimy, co zostanie zablokowane, a co pozostanie dozwolone. Dopiero wtedy ją aktywujemy.",
    ),
    scene(
        "blocked",
        7,
        "Stop it before\ninference.",
        "The same Hello is now blocked locally. No business model call.",
        "01 / CONTROL",
        "Policy v4 → v5 · same process · no restart",
        "video",
        (920, 210, 640, 675),
        32,
        "To samo Hello jest już blokowane lokalnie. Model biznesowy nie został wywołany. Zmieniła się polityka, nie kod agenta.",
    ),
    scene(
        "audit",
        6,
        "Know why.\nProve what ran.",
        "A decision is useful when you can explain its boundary.",
        "02 / VISIBILITY",
        "Recorded decisions · policy version · execution status",
        "demo-audit.png",
        (255, 80, 1325, 790),
        voice="Każda decyzja zostawia ślad: przyczynę, wersję polityki i informację, czy wywołanie rzeczywiście wykonano.",
    ),
    scene(
        "language",
        9,
        "Policies in\nyour words.",
        "Describe the restriction and its exception. Supply examples that must pass.",
        "03 / LAYA",
        "Scoped input/output policy · explicit sample review",
        "demo-semantic-rule.png",
        (0, 0, 700, 810),
        voice="Politykę semantyczną zapisujemy własnymi słowami. Określamy zakaz, wyjątek i oczekiwane wyniki przykładów.",
    ),
    scene(
        "review",
        12,
        "Test before\nyou trust.",
        "8 scoped cases passed before activation. Input and output. Models and tools.",
        "03 / LAYA",
        "Before / after review · explicit confirmation · saved regressions",
        "video",
        (450, 45, 700, 810),
        65.7,
        "Laya porównuje aktywną i proponowaną politykę. Osiem przypadków przechodzi testy. Aktywacja wymaga potwierdzenia, a przykłady zostają do regresji.",
    ),
    scene(
        "document",
        8,
        "Keep the value.\nProtect the data.",
        "A two-page PDF contains useful content and contact details.",
        "04 / DOCUMENTS",
        "Synthetic source document · separate recorded OCR session",
        "demo-document-preview.png",
        (0, 0, 1600, 900),
        voice="Dokument zawiera użyteczną treść i dane kontaktowe. Nie musimy rezygnować z jego przetwarzania.",
    ),
    scene(
        "redact",
        12,
        "Useful text.\nHidden contacts.",
        "Local OCR. Two pages. Two email redactions. Downloadable Markdown.",
        "04 / DOCUMENTS",
        "Exact UI download · [REDACTED:pii_email] x 2",
        "demo-ocr-markdown.png",
        (925, 210, 625, 690),
        voice="OCR lokalnie odczytuje obie strony. Polityka usuwa dwa adresy e-mail. Dostajemy użyteczny Markdown, który można pobrać lub przekazać dalej.",
    ),
    scene(
        "answer",
        10,
        "Let the model\ndo useful work.",
        "Only protected Markdown goes to Qwen. Laya checks both directions.",
        "04 / DOCUMENTS",
        "Protected Markdown · input and output checks",
        "video",
        (920, 345, 640, 540),
        134.9,
        "Do Qwena trafia chroniony tekst, nie oryginalny PDF. Model tworzy podsumowanie, a Laya sprawdza wejście i odpowiedź.",
    ),
    scene(
        "operations",
        10,
        "Safe policy\nchanges.",
        "Dynamic protection. Predictable operations.",
        "REGRESSION-TESTED BEHAVIOR",
        "Verified behavior · editorial summary, not a live UI recording",
        voice="Błędna aktualizacja zachowuje ostatnią poprawną politykę. Kolejka sprawdza aktualne reguły przed wykonaniem. Ponowne uruchomienie zachowuje konfigurację i klucze.",
    ),
    scene(
        "close",
        9,
        "Your agents.\nYour policies.",
        "Start locally with one command.",
        "FASTFENCE",
        "Requires uv and a running Ollama service · first run installs local components",
        voice="FastFence daje kontrolę nad agentami bez przepisywania aplikacji. Uruchom lokalnie jednym poleceniem i sprawdź na własnych regułach.",
    ),
]


def base(index, item):
    image = Image.new("RGB", (1920, 1080), NAVY)
    draw = ImageDraw.Draw(image)
    draw.line((70, 94, 1850, 94), fill="#24404A", width=2)
    text(draw, (70, 39), "FASTFENCE", 28, TEAL, True)
    text(draw, (1340, 43), "EDITED PRODUCT DEMONSTRATION", 21, MUTED)
    text(draw, (70, 144), item["label"], 23, TEAL, True)
    if item["id"] not in {"hook", "close"}:
        text(draw, (70, 220), item["title"], 65, WHITE, True)
        text(draw, (75, 432), item["body"], 32, MUTED, width=29)
        draw.line((75, 714, 585, 714), fill="#24404A", width=2)
        text(draw, (75, 742), item["proof"], 23, TEAL, width=36)
    text(
        draw,
        (70, 1023),
        (
            "REGRESSION-TESTED PRODUCT BEHAVIOR  /  EDITORIAL SUMMARY"
            if item["id"] == "operations"
            else "REAL CAPTURE  /  PUBLIC PACKAGE 1.0.7  /  NO MOCK RESPONSES"
        ),
        20,
        MUTED,
    )
    text(draw, (1700, 1021), f"{index + 1:02d} / {len(SCENES):02d}", 23, WHITE)
    draw.rectangle(
        (0, 1072, round(1920 * (index + 1) / len(SCENES)), 1079), fill=TEAL
    )
    return image, draw


def compose_static(index, item):
    image, draw = base(index, item)
    if item["id"] == "hook":
        text(draw, (70, 215), "Same request. New policy.", 86, WHITE, True)
        text(draw, (75, 329), item["body"], 38, MUTED)
        for x, name, label, color in [
            (75, "demo-allowed.png", "BEFORE  /  ALLOWED", TEAL),
            (1000, "demo-blocked.png", "AFTER  /  BLOCKED", "#FFA886"),
        ]:
            text(draw, (x, 422), label, 30, color, True)
            panel = (
                Image.open(ASSETS / name)
                .convert("RGB")
                .crop((925, 277, 1545, 577))
            )
            panel = panel.resize((840, 407), Image.Resampling.LANCZOS)
            image.paste(panel, (x, 480))
        text(draw, (75, 922), item["proof"], 28, TEAL)
    elif item["id"] == "close":
        text(draw, (75, 225), item["title"], 100, WHITE, True)
        text(draw, (1040, 263), "uv tool run fastfence", 50, TEAL, True)
        text(
            draw,
            (1040, 365),
            "Start locally. Set your rules.\nSee every decision.",
            39,
            WHITE,
        )
        text(draw, (1040, 551), "fastfence.dev", 52, TEAL, True)
        text(draw, (80, 808), item["proof"], 25, MUTED)
        text(
            draw,
            (80, 863),
            "Cuts omit navigation and waiting. Playback is 1x. Original recording retained.",
            23,
            MUTED,
        )
        logo = Image.open(ASSETS / "showcase-logo.png").convert("RGBA")
        logo.thumbnail((160, 160), Image.Resampling.LANCZOS)
        image.paste(logo, (80, 581), logo)
        text(draw, (275, 620), "FastFence", 62, WHITE, True)
    elif item["id"] == "operations":
        for y, number, title, body in [
            (183, "01", "Invalid update", "Last valid policy stays active."),
            (
                442,
                "02",
                "Queued request",
                "Current rules checked before execution.",
            ),
            (
                701,
                "03",
                "Idempotent setup",
                "Configuration and keys preserved.",
            ),
        ]:
            draw.rounded_rectangle(
                (730, y, 1830, y + 212), radius=20, fill="#12313B"
            )
            text(draw, (766, y + 35), number, 25, TEAL, True)
            text(draw, (835, y + 32), title, 39, WHITE, True)
            text(draw, (835, y + 113), body, 33, MUTED)
    elif item["source"] != "video":
        original = Image.open(ASSETS / item["source"]).convert("RGB")
        x, y, w, h = item["crop"]
        panel = original.crop((x, y, x + w, y + h))
        scale = min(1170 / w, 830 / h)
        panel = panel.resize(
            (round(w * scale), round(h * scale)), Image.Resampling.LANCZOS
        )
        image.paste(
            panel,
            (700 + (1170 - panel.width) // 2, 135 + (830 - panel.height) // 2),
        )
    return image


def mux_soundtrack(target, duration):
    track = OUTPUT / "fastfence-soundtrack.m4a"
    if not track.exists():
        return {"type": "none", "voice": False}
    silent = BUILD / "fastfence-demo-v2-silent.mp4"
    target.replace(silent)
    run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(silent),
            "-i",
            str(track),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-t",
            str(duration),
            "-movflags",
            "+faststart",
            str(target),
        ]
    )
    return {
        "type": "original_instrumental",
        "source_track": track.name,
        "voice": False,
        "source_samples": "original synthesis",
    }


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    timeline, paths, elapsed = [], [], 0
    for index, item in enumerate(SCENES):
        background = BUILD / f"scene-{index:02d}.png"
        compose_static(index, item).save(background)
        target = BUILD / f"scene-{index:02d}.mp4"
        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(background),
        ]
        filters = ""
        if item["source"] == "video":
            command += ["-ss", str(item["source_start"]), "-i", str(SOURCE)]
            x, y, w, h = item["crop"]
            scale = min(1170 / w, 830 / h)
            sw, sh = round(w * scale / 2) * 2, round(h * scale / 2) * 2
            px, py = 700 + (1170 - sw) // 2, 135 + (830 - sh) // 2
            filters = f"[1:v]crop={w}:{h}:{x}:{y},scale={sw}:{sh}[e];[0:v][e]overlay={px}:{py}:shortest=1[v];"
        else:
            filters = f"[0:v]zoompan=z='1+0.012*on/{item['duration'] * 30}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s=1920x1080:fps=30[v];"
        filters += f"[v]fade=t=in:st=0:d=0.18,fade=t=out:st={item['duration'] - 0.18}:d=0.18[out]"
        command += [
            "-filter_complex_threads",
            "1",
            "-filter_complex",
            filters,
            "-map",
            "[out]",
            "-an",
            "-t",
            str(item["duration"]),
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
        thumbnail = BUILD / f"thumbnail-{index:02d}.jpg"
        run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-ss",
                str(item["duration"] / 2),
                "-i",
                str(target),
                "-frames:v",
                "1",
                str(thumbnail),
            ]
        )
        timeline.append(
            {
                **item,
                "start_seconds": elapsed,
                "end_seconds": elapsed + item["duration"],
                "playback_speed": 1,
            }
        )
        elapsed += item["duration"]
        paths.append(target)
        sys.stdout.write(f"Rendered {index + 1}/{len(SCENES)}: {item['id']}\n")
        sys.stdout.flush()
    concat = BUILD / "concat.txt"
    concat.write_text("\n".join(f"file '{p}'" for p in paths))
    target = OUTPUT / "fastfence-demo-v2.mp4"
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
            str(target),
        ]
    )
    audio = mux_soundtrack(target, elapsed)
    (OUTPUT / "demo-v2-timeline.json").write_text(
        json.dumps(
            {
                "duration_seconds": elapsed,
                "resolution": "1920x1080",
                "audio": audio,
                "source_recording": "fastfence-demo.mp4",
                "source_evidence": "demo-evidence.json",
                "editing": "Editorial layouts, unchanged UI crops and real-time excerpts; cuts omit waits/navigation. No acceleration, no voice, no fabricated UI.",
                "semantic_review_scope": "Financial example already blocked by base policy; this sequence demonstrates reviewed coverage, not a newly caused verdict change or arbitrary-rule guarantee.",
                "scenes": timeline,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    sheet = Image.new("RGB", (1280, 1080), NAVY)
    for index in range(len(SCENES)):
        tile = Image.open(BUILD / f"thumbnail-{index:02d}.jpg").resize(
            (640, 360)
        )
        # Two contact sheets preserve legibility at a useful inspection size.
        if index % 6 == 0:
            sheet = Image.new("RGB", (1280, 1080), NAVY)
        sheet.paste(tile, ((index % 2) * 640, ((index % 6) // 2) * 360))
        if index % 6 == 5:
            sheet.save(BUILD / f"contact-sheet-{index // 6 + 1}.jpg")
    sys.stdout.write(
        json.dumps({"video": str(target), "duration_seconds": elapsed}) + "\n"
    )


if __name__ == "__main__":
    main()
