"""Zoom into one x-range of several taskbar strips and stack them for reading.

Usage:
    python diag_crop.py X0 X1 ZOOM name1.png name2.png ...
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def main() -> int:
    x0, x1, zoom = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    names = sys.argv[4:]
    rows = []
    for name in names:
        image = Image.open(os.path.join(OUT, name)).convert("RGB")
        crop = image.crop((x0, 0, min(x1, image.width), image.height))
        rows.append((name, crop.resize((crop.width * zoom, crop.height * zoom), Image.NEAREST)))

    gap = 10
    width = max(row[1].width for row in rows)
    height = sum(row[1].height for row in rows) + gap * (len(rows) - 1)
    canvas = Image.new("RGB", (width + 60, height), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    y = 0
    for name, image in rows:
        canvas.paste(image, (60, y))
        draw.text((2, y + image.height // 2 - 4), name.replace("accept-", "").replace("-taskbar.png", ""), fill=(255, 255, 0))
        # ruler every 50 px of original coordinates
        for x in range(x0 - x0 % 50 + 50, x1, 50):
            px = 60 + (x - x0) * zoom
            draw.line((px, y, px, y + 5), fill=(255, 0, 0))
            draw.text((px + 1, y), str(x), fill=(255, 80, 80))
        y += image.height + gap

    path = os.path.join(OUT, f"crop-{x0}-{x1}.png")
    canvas.save(path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
