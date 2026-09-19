"""Diff two ``compare_layout.py`` snapshots and report where the port drifted.

``compare_layout.py`` prints one page for one front end.  Reading two of those
tables side by side is how the guide page's 5px drift went unnoticed for so
long: the numbers were all there, but nothing subtracted them.

This pairs the rows of ``out/layout-tk-<page>.json`` with
``out/layout-qt-<page>.json`` and prints the vertical delta of every matched
widget.  Widgets are matched on their text first (the guide page's labels are
all unique) and fall back to document order within the same depth, so a page
with no text - 官方登录 - still diffs.

    "C:/Program Files/Develop/Python/python.exe" prototypes/compare_layout.py --framework tk --page guide
    "C:/Program Files/Develop/Python/python.exe" prototypes/compare_layout.py --framework qt --page guide
    "C:/Program Files/Develop/Python/python.exe" prototypes/compare_layout_diff.py --page guide

``--tolerance`` sets the number of pixels that still counts as "in place"
(default 1, because a QSS border is drawn inside a widget's box while Tk's
``highlightthickness`` is added outside it - a 1px offset is expected there).

Exit code is 0 when every page is within tolerance, 1 otherwise, so this can be
wired into the acceptance run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
PAGES = ("current", "profiles", "official", "guide", "recommended")

# The content column only; the sidebar is identical in both front ends.
CONTENT_LEFT = 150


def load(framework: str, page: str) -> list:
    path = OUT / f"layout-{framework}-{page}.json"
    if not path.exists():
        raise SystemExit(f"missing {path} - run compare_layout.py for both front ends first")
    return json.loads(path.read_text(encoding="utf-8"))


def visible(rows: list) -> list:
    """The rows a human can see, in document order.

    ``compare_layout.py`` filters these out of its own table, and the filter has
    to match: a 1px-tall separator or a zero-width spacer is still laid out, but
    it is not something the eye can compare.
    """
    kept = [
        r
        for r in rows
        if r["x"] + r["w"] > CONTENT_LEFT and r["w"] > 1 and r["h"] > 1 and r["y"] >= 0
    ]
    kept.sort(key=lambda r: (r["y"], r["x"]))
    return kept


def key(row: dict) -> tuple:
    """Match on text when there is any, else on the widget's family.

    The text is the strongest signal - the guide page's two ``切换配置`` bullets
    share a class and a depth, and only the text tells them apart.

    Widgets with no text fall back to their family alone, deliberately *not*
    including the depth: the two toolkits nest the same control differently
    (Tk's ``Treeview`` sits at depth 3, Qt's ``QTableWidget`` at depth 2, and the
    Qt one carries a ``QHeaderView`` sibling that Tk has no object for), so a
    depth in the key pairs the wrong widgets.  Same-family rows are consumed in
    the order they were laid out.
    """
    text = (row.get("text") or "").strip()
    if text:
        return ("text", text)
    return ("shape", FAMILIES.get(row["class"], row["class"]))


# Tk class -> family, Qt class -> family.  Anything absent is its own family.
FAMILIES = {
    "Label": "label",
    "QLabel": "label",
    "TEntry": "entry",
    "QLineEdit": "entry",
    "TButton": "button",
    "QPushButton": "button",
    "QToolButton": "button",
    "Treeview": "table",
    "QTableWidget": "table",
    # The header is not a table: it is the column strip Tk draws inside the
    # Treeview and Qt hoists into a sibling widget.
    "QHeaderView": "header",
    "Canvas": "canvas",
    "DotLabel": "canvas",
    "QScrollBar": "scrollbar",
}


# Containers have no counterpart across the two toolkits - a Tk ``Frame`` with
# ``pack`` has no Qt equivalent object, and Qt grows a scroll-area hierarchy that
# Tk never creates.  They are expected to stay unmatched, so they are reported
# but do not count against a page.
CONTAINERS = {
    "Frame",
    "Toplevel",
    "QWidget",
    "QFrame",
    "QScrollArea",
    "QStackedWidget",
    "QAbstractScrollArea",
}


def is_container(row: dict) -> bool:
    name = row.get("name") or ""
    # Qt's scroll-area plumbing is QWidgets with generated object names, and a
    # custom QFrame subclass is still a container.
    if name.startswith("qt_scrollarea"):
        return True
    cls = row["class"]
    if cls in CONTAINERS:
        return True
    return cls.endswith(("Card", "Panel", "Holder"))


# Rows that legitimately have no counterpart, with the reason.  Listing them
# explicitly - rather than widening the container test until they disappear -
# keeps the run honest: anything *not* in here is a new finding.  A pair that
# exists on both sides under different families needs an entry for each class.
EYE_TOGGLE = (
    "the API-key eye toggle: Tk draws it as a tk.Label (24x20), Qt gets the internal "
    "QToolButton that QLineEdit.addAction() creates (22x18)"
)
KNOWN_UNPAIRED = {
    "current": {"Label": EYE_TOGGLE, "QToolButton": EYE_TOGGLE},
    "profiles": {
        "Canvas": "the tree's scrollbar: Tk draws it as a Canvas, Qt hides its own",
        "QHeaderView": (
            "the column strip: Tk draws it inside the Treeview, Qt hoists it into a sibling"
        ),
    },
}


def known_unpaired(page: str, row: dict) -> str | None:
    return KNOWN_UNPAIRED.get(page, {}).get(row["class"])


def pair(tk_rows: list, qt_rows: list) -> tuple[list, list, list]:
    """Return (matched, tk_only, qt_only).

    Each matched entry is ``(tk_row, qt_row)``.  Order is preserved by consuming
    the Qt list front-to-back, so two identical keys pair in the order they were
    laid out rather than arbitrarily.
    """
    buckets: dict[tuple, list] = {}
    for row in qt_rows:
        buckets.setdefault(key(row), []).append(row)

    matched: list = []
    tk_only: list = []
    for row in tk_rows:
        bucket = buckets.get(key(row))
        if bucket:
            matched.append((row, bucket.pop(0)))
        else:
            tk_only.append(row)
    qt_only = [row for bucket in buckets.values() for row in bucket]
    return matched, tk_only, qt_only


def describe(row: dict) -> str:
    name = row.get("name") or ""
    text = (row.get("text") or "")[:34]
    label = row["class"] + (f"[{name}]" if name else "")
    return f"{label}  {text!r}" if text else label


def report(page: str, tolerance: int, verbose: bool) -> tuple[int, int, list]:
    """Print one page's diff.  Returns (issues, worst_dy, unpaired_suspects)."""
    tk_rows = visible(load("tk", page))
    qt_rows = visible(load("qt", page))
    matched, tk_only, qt_only = pair(tk_rows, qt_rows)

    print(f"\n=== {page} ===")
    worst = 0
    drift = 0
    for tk_row, qt_row in matched:
        dy = qt_row["y"] - tk_row["y"]
        dh = qt_row["h"] - tk_row["h"]
        worst = max(worst, abs(dy))
        flag = ""
        if abs(dy) > tolerance or abs(dh) > tolerance:
            drift += 1
            flag = "  <-- drift"
        if flag or verbose:
            print(
                f"  y {tk_row['y']:>4} -> {qt_row['y']:>4} ({dy:+3})   "
                f"h {tk_row['h']:>4} -> {qt_row['h']:>4} ({dh:+3})   {describe(tk_row)}{flag}"
            )

    # Unmatched rows: containers are expected, and a few are known to have no
    # counterpart at all.  Anything left over wants a look.
    suspects: list = []
    known: list = []
    for tag, rows in (("Tk-only", tk_only), ("Qt-only", qt_only)):
        for row in rows:
            if is_container(row):
                continue
            reason = known_unpaired(page, row)
            (known if reason else suspects).append((tag, row, reason))

    structural = len(tk_only) + len(qt_only) - len(suspects) - len(known)
    for tag, row, reason in known:
        print(f"  {tag} (known): {describe(row)}  y={row['y']} h={row['h']}  - {reason}")
    for tag, row, _reason in suspects:
        print(f"  {tag} (unpaired): {describe(row)}  y={row['y']} h={row['h']}")

    verdict = "CLEAN" if not drift and not suspects else f"{drift} drifting, {len(suspects)} unpaired"
    print(
        f"  {len(matched)} paired, worst |dy| = {worst}px, "
        f"{structural} container(s) without a counterpart  ->  {verdict}"
    )
    return drift + len(suspects), worst, suspects


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", choices=PAGES, help="one page; default is all five")
    parser.add_argument("--tolerance", type=int, default=1, help="pixels that still count as in place")
    parser.add_argument("--verbose", action="store_true", help="print matched rows even when clean")
    args = parser.parse_args()

    pages = (args.page,) if args.page else PAGES
    total = 0
    worst_all = 0
    for page in pages:
        issues, worst, _suspects = report(page, args.tolerance, args.verbose)
        total += issues
        worst_all = max(worst_all, worst)
    print(f"\nworst |dy| across the run: {worst_all}px")
    print("ALL PAGES IN PLACE" if total == 0 else f"{total} row(s) need attention")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
