"""Put the Tk and Qt front ends side by side, zoomed, for a named region.

Layout fidelity is not a structural property.  Three green suites (the
structural smoke test, the 78 interactive assertions and the flash probe) all
passed on a build with a 200px hole in its pages and reversed window buttons,
because a widget can be present, correctly named and correctly wired while
sitting in the wrong place.  The only honest check is two images side by side,
and this makes producing them a command instead of an afternoon.

    "C:/Program Files/Develop/Python/python.exe" prototypes/compare_screens.py

Requires ``out/tour-<page>.png`` and ``out/tk-tour-<page>.png``, i.e. run
``qt_visual_tour.py`` and ``tk_visual_tour.py`` first.  Writes
``out/cmp-<region>.png``: Tk on the left, Qt on the right, with a 1px separator.

Regions are given in absolute pixels because both windows are 820x500 and the
tour shots capture the whole window in both cases.  The table header is located
by colour rather than hardcoded, since it is the one region whose position moves
with the table's content.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

from PIL import Image, ImageDraw  # noqa: E402

# (page, left, top, right, bottom, zoom)
REGIONS: dict[str, tuple[str, int, int, int, int, int]] = {
    # The five nav rows: 38px title bar, then 5 rows of 42px.
    "sidebar": ("profiles", 0, 38, 142, 38 + 5 * 42, 3),
}

HEADER_BG = (238, 240, 242)  # #eef0f2, the Treeview.Heading background
# The band is not one colour.  Tk's themed heading paints a 1px ``#eeebe7``
# highlight and a 1px ``#cfcdc8`` shadow *inside* its 35px band, so a locator
# that accepts only the fill measures Tk's band as 31px against Qt's 33px and
# reports a phantom 1px drift on a header whose extent actually matches exactly.
HEADER_BAND = {
    HEADER_BG,
    (238, 235, 231),  # #eeebe7 highlight
    (207, 205, 200),  # #cfcdc8 shadow
}


def locate_table_header(image: Image.Image) -> tuple[int, int, int, int] | None:
    """Find the table header band on the 切换配置 page.

    Hardcoding y would silently point at the wrong band the moment the page's
    content shifts, which is exactly the class of mistake this script exists to
    catch.      So: a row belongs to the header if most of its width is painted one of the
    header's band colours, and the band is the longest run of such rows.  Counting
    across the width rather than sampling one column matters - the header's own
    text sits in the middle of the band, and a single-column scan walks straight
    into a glyph and stops early.
    """
    span = range(200, min(image.width - 20, 780))
    rows = [
        y
        for y in range(60, image.height - 40)
        if sum(1 for x in span if image.getpixel((x, y))[:3] in HEADER_BAND) > 0.6 * len(span)
    ]
    if not rows:
        return None
    # Longest consecutive run.
    best = run = [rows[0]]
    for y in rows[1:]:
        run = run + [y] if y == run[-1] + 1 else [y]
        if len(run) > len(best):
            best = run
    top, bottom = best[0], best[-1]
    # Extend horizontally along a row near the top of the band, above the text.
    probe_y = min(top + 2, bottom)
    left = min(span)
    while left > 0 and image.getpixel((left - 1, probe_y))[:3] in HEADER_BAND:
        left -= 1
    right = max(span)
    while right + 1 < image.width and image.getpixel((right + 1, probe_y))[:3] in HEADER_BAND:
        right += 1
    return (left - 4, top - 4, right + 5, bottom + 5)


def load(page: str, framework: str) -> Image.Image:
    name = f"tk-tour-{page}.png" if framework == "tk" else f"tour-{page}.png"
    path = OUT / name
    if not path.exists():
        raise SystemExit(f"missing {path} - run the visual tours first")
    return Image.open(path).convert("RGB")


def compose(region: str, boxes: dict[str, tuple[int, int, int, int]], zoom: int) -> Path:
    """Tk on the left, Qt on the right, each cropped at its *own* location.

    Passing one box to both is the trap this function exists to avoid: the two
    builds have drifted a few pixels apart vertically in places, so a shared box
    crops two different bands and the resulting image shows a difference that is
    really just the crop.  Locating the region per framework separates "the
    header looks wrong" from "the header is 9px higher".
    """
    page = REGIONS[region][0] if region in REGIONS else "profiles"
    tk = load(page, "tk").crop(boxes["tk"])
    qt = load(page, "qt").crop(boxes["qt"])
    width = (boxes["tk"][2] - boxes["tk"][0]) * zoom
    height = (boxes["tk"][3] - boxes["tk"][1]) * zoom
    canvas = Image.new("RGB", (width * 2 + 3, height), (255, 0, 0))
    canvas.paste(tk.resize((width, height), Image.NEAREST), (0, 0))
    canvas.paste(qt.resize((width, height), Image.NEAREST), (width + 3, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((4, 4), "TK", fill=(200, 0, 0))
    draw.text((width + 7, 4), "QT", fill=(200, 0, 0))
    target = OUT / f"cmp-{region}.png"
    canvas.save(target)
    return target


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    made = 0

    for region, (_page, left, top, right, bottom, zoom) in REGIONS.items():
        box = (left, top, right, bottom)
        target = compose(region, {"tk": box, "qt": box}, zoom)
        print(f"  {region:10s} -> {target.name}  ({right - left}x{bottom - top} @ {zoom}x)")
        made += 1

    # The table header, located in each build rather than assumed.
    page = "profiles"
    boxes: dict[str, tuple[int, int, int, int]] = {}
    for framework in ("tk", "qt"):
        found = locate_table_header(load(page, framework))
        if found is None:
            print(f"  thead      -> [skip] no #eef0f2 band in the {framework} shot")
            return 1 if not made else 0
        boxes[framework] = found
    target = compose("thead", boxes, 4)
    print(f"  thead      -> {target.name}  @ 4x")
    for framework, box in boxes.items():
        print(
            f"      {framework}: y={box[1] + 4}..{box[3] - 5} "
            f"({box[3] - box[1] - 8}px tall), x={box[0] + 4}..{box[2] - 5}"
        )
    drift = boxes["qt"][1] - boxes["tk"][1]
    print(f"      vertical drift: Qt header sits {drift:+d}px vs Tk")
    made += 1

    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
