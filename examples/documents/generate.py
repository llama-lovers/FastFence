"""Generate synthetic PL/EN documents: never use customer source material."""

import argparse
import importlib
from pathlib import Path

TEXT = (
    "English invoice FIRST PAGE\nCustomer Alice Example\nEmail alice@example.com\nTotal 123.45 USD",
    "Polski dokument DRUGA STRONA\nZażółć gęślą jaźń\nNumer 44051401458\nKwota 250.00 PLN",
)


def generate(output: Path, font_path: Path) -> None:
    image = importlib.import_module("PIL.Image")
    drawing = importlib.import_module("PIL.ImageDraw")
    fonts = importlib.import_module("PIL.ImageFont")
    font = fonts.truetype(str(font_path), 42)
    output.mkdir(parents=True, exist_ok=True)
    pages = []
    for text in TEXT:
        page = image.new("RGB", (1400, 700), "white")
        drawing.Draw(page).multiline_text(
            (70, 70), text, font=font, fill="black", spacing=35
        )
        pages.append(page)
    pages[0].save(output / "english.png")
    pages[1].save(output / "polish.jpg", quality=95)
    pages[0].rotate(90, expand=True).save(output / "rotated.png")
    pages[0].save(
        output / "two-pages.pdf",
        save_all=True,
        append_images=pages[1:],
        resolution=144,
    )
    canvas = importlib.import_module("reportlab.pdfgen.canvas").Canvas
    reader = importlib.import_module("reportlab.lib.utils").ImageReader
    document = canvas(
        str(output / "mixed.pdf"), pagesize=(700, 350), invariant=1
    )
    document.setFont("Helvetica", 21)
    for index, line in enumerate(TEXT[0].splitlines()):
        document.drawString(35, 300 - index * 38, line)
    document.showPage()
    document.drawImage(reader(pages[1]), 0, 0, width=700, height=350)
    document.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("examples/documents")
    )
    parser.add_argument(
        "--font",
        type=Path,
        default=Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    )
    arguments = parser.parse_args()
    generate(arguments.output, arguments.font)
