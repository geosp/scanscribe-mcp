"""Make the self-made PDFs for the Docker GPU check: 10 English pages and 2 French pages.

    uv run python docs/demos/2026-11-22-docker-gpu-check/make_pdfs.py /tmp/docker-gpu-check

Writes en.pdf and fr.pdf, and next to each the expected text (en.expected.txt, fr.expected.txt)
in get_ocr_result's format, to compare with the OCR. No book material: every sentence is written
for this check.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DPI = 200

EN = [
    [
        f"Docker check, English page {n}.",
        f"This page was drawn by a script for page {n} of 10.",
        "The quick brown fox jumps over the lazy dog.",
        f"Numbers on this page: {n * 7}, {n * 111} and {n * 2024}.",
    ]
    for n in range(1, 11)
]

FR = [
    [
        "Contrôle Docker, page française une.",
        "Cette page a été dessinée par un script.",
        "Le serveur traite une tâche à la fois.",
    ],
    [
        "Deuxième page : les nombres 12, 345 et 6789.",
        "Fin du contrôle en français.",
    ],
]


# A TrueType font with accented letters: Pillow's built-in font draws empty boxes for "ô" or
# "é". The first one found is used; pass FONT=<path.ttf> to choose another.
FONTS = [
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",  # Fedora
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Debian, Ubuntu
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font_path() -> str:
    for path in [os.environ.get("FONT", ""), *FONTS]:
        if path and Path(path).is_file():
            return path
    raise SystemExit("no TrueType font with accents found; pass FONT=<path.ttf>")


def write(target: Path, pages: list[list[str]]) -> None:
    font = ImageFont.truetype(font_path(), size=48)
    images = []
    for lines in pages:
        page = Image.new("RGB", (int(8.5 * DPI), 11 * DPI), "white")
        draw = ImageDraw.Draw(page)
        for row, line in enumerate(lines):
            draw.text((150, 200 + row * 110), line, fill="black", font=font)
        images.append(page)
    images[0].save(target, "PDF", resolution=DPI, save_all=True, append_images=images[1:])
    expected = "\n\n".join(
        f"--- Page {n} ---\n" + "\n".join(lines) for n, lines in enumerate(pages, 1)
    )
    target.with_suffix(".expected.txt").write_text(expected, encoding="utf-8")
    print(f"wrote {target} ({len(pages)} pages, font {Path(font_path()).name})")


def main() -> None:
    folder = Path(sys.argv[1]).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    write(folder / "en.pdf", EN)
    write(folder / "fr.pdf", FR)


if __name__ == "__main__":
    main()
