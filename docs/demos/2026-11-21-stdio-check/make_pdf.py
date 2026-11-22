"""Make a small self-made PDF for the stdio manual check: a few pages of known English text.

    uv run python docs/demos/2026-11-21-stdio-check/make_pdf.py /tmp/stdio-check/check.pdf

Writes the PDF and, next to it, `expected.txt` with each page's lines, to compare with the OCR.
No book material: the sentences are written for this check.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAGES = [
    [
        "Manual check for scanscribe-mcp.",
        "This page was drawn by a script.",
        "The quick brown fox jumps over the lazy dog.",
    ],
    [
        "Page two holds numbers: 12, 345 and 6789.",
        "Each page starts with its own marker line.",
        "The server runs one job at a time.",
    ],
    [
        "The last page is short.",
        "End of the check.",
    ],
]

DPI = 200


def main() -> None:
    target = Path(sys.argv[1]).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=48)
    images = []
    for lines in PAGES:
        page = Image.new("RGB", (int(8.5 * DPI), 11 * DPI), "white")
        draw = ImageDraw.Draw(page)
        for row, line in enumerate(lines):
            draw.text((150, 200 + row * 110), line, fill="black", font=font)
        images.append(page)
    images[0].save(target, "PDF", resolution=DPI, save_all=True, append_images=images[1:])
    expected = "\n\n".join(
        f"--- Page {n} ---\n" + "\n".join(lines) for n, lines in enumerate(PAGES, 1)
    )
    # No final newline: get_ocr_result writes format_pages output exactly, without one.
    (target.parent / "expected.txt").write_text(expected, encoding="utf-8")
    print(f"wrote {target} ({len(PAGES)} pages) and {target.parent / 'expected.txt'}")


if __name__ == "__main__":
    main()
