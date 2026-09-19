"""One image with the three reported elements, Tk above Qt, for a human to check.

``compare_screens.py`` produces one region at a time.  When a round of fixes touches three different
controls it is the *set* that has to be looked at, because that is how a human reviews it - and
because a fix that makes one element match while shifting its neighbour is only visible in context.

    "C:/Program Files/Develop/Python/python.exe" prototypes/compare_round.py

Requires the two visual tours to have run.  Writes ``out/cmp-round.png``: three rows, each Tk above
Qt, labelled, with a 1px separator between rows.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image, ImageDraw  # noqa: E402

import compare_screens  # noqa: E402

OUT = HERE / "out"
LABEL_W = 96
GAP = 10
PAD = 6


def label(text: str, width: int, height: int, background=(243, 244, 247)) -> Image.Image:
    tile = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(tile)
    draw.text((4, max(0, height // 2 - 6)), text, fill=(32, 36, 43))
    return tile


def zoom(image: Image.Image, factor: int) -> Image.Image:
    return image.resize((image.width * factor, image.height * factor), Image.NEAREST)


def pair(region: str, factor: int) -> Image.Image:
    """Tk crop above Qt crop, each taken at its own located position.

    A region listed in ``compare_screens.REGIONS`` uses that fixed box for both
    builds; anything else (the table header) is located per framework by colour,
    because the two builds have drifted apart vertically and one shared box would
    crop two different bands.
    """
    if region in compare_screens.REGIONS:
        page, left, top, right, bottom, _zoom = compare_screens.REGIONS[region]
        shots = {fw: compare_screens.load(page, fw) for fw in ("tk", "qt")}
        boxes = {fw: (left, top, right, bottom) for fw in ("tk", "qt")}
    else:
        shots = {fw: compare_screens.load("profiles", fw) for fw in ("tk", "qt")}
        boxes = {fw: compare_screens.locate_table_header(img) for fw, img in shots.items()}
    tiles = []
    for fw in ("tk", "qt"):
        found = boxes[fw]
        if found is None:
            raise SystemExit(f"could not locate {region} in the {fw} shot")
        tiles.append(zoom(shots[fw].crop(found), factor))
    width = max(t.width for t in tiles)
    height = sum(t.height for t in tiles) + GAP
    canvas = Image.new("RGB", (LABEL_W + width, height), (255, 0, 0))
    canvas.paste(label(region, LABEL_W, height), (0, 0))
    canvas.paste(label("TK", width, 14, (255, 255, 255)), (LABEL_W, 0))
    canvas.paste(tiles[0], (LABEL_W, 14))
    canvas.paste(label("QT", width, 14, (255, 255, 255)), (LABEL_W, tiles[0].height + GAP))
    canvas.paste(tiles[1], (LABEL_W, tiles[0].height + GAP + 14))
    return canvas


def combo_pair() -> Image.Image:
    """The combo's right-hand end: the arrow zone plus a little of the field."""
    TAIL = 44
    tiles = []
    for name in ("combo-tk.png", "combo-qt.png"):
        path = OUT / name
        if not path.exists():
            raise SystemExit(f"missing {path} - run probe_combo_arrow.py for both frameworks")
        shot = Image.open(path).convert("RGB")
        # The two fields are different widths (Tk's `width=39` chars vs Qt's minimumWidth), so
        # align them on their right edges rather than their left.
        tiles.append(shot.crop((shot.width - TAIL * 4, 0, shot.width, shot.height)))
    width = max(t.width for t in tiles)
    height = sum(t.height for t in tiles) + GAP
    canvas = Image.new("RGB", (LABEL_W + width, height), (255, 0, 0))
    canvas.paste(label("combo", LABEL_W, height), (0, 0))
    canvas.paste(label("TK", width, 14, (255, 255, 255)), (LABEL_W, 0))
    canvas.paste(tiles[0], (LABEL_W, 14))
    canvas.paste(label("QT", width, 14, (255, 255, 255)), (LABEL_W, tiles[0].height + GAP))
    canvas.paste(tiles[1], (LABEL_W, tiles[0].height + GAP + 14))
    return canvas


def main() -> int:
    rows = [
        pair("sidebar", 2),
        pair("thead", 3),
        combo_pair(),
    ]
    width = max(r.width for r in rows) + PAD * 2
    height = sum(r.height for r in rows) + PAD * (len(rows) + 1) + 2 * (len(rows) - 1)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    y = PAD
    for row in rows:
        canvas.paste(row, (PAD, y))
        y += row.height + PAD
        if row is not rows[-1]:
            ImageDraw.Draw(canvas).line([(0, y - PAD // 2), (width, y - PAD // 2)], fill=(230, 232, 235))
    target = OUT / "cmp-round.png"
    canvas.save(target)
    print(f"  wrote {target.name}  ({canvas.width}x{canvas.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
