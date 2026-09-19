"""Which gradient values does Qt's QSS parser actually accept on a header section?

Tk's themed heading carries a 1px ``#eeebe7`` highlight and a 1px ``#cfcdc8``
shadow inside its 35px band, and the stylesheet is the obvious place to reproduce
them.  It cannot be done: ``qlineargradient``'s stop positions are parsed as
**0 or 1 only**, so the fractional and percentage forms a 1-in-33 band needs
collapse the whole declaration to a flat colour - silently, with no warning from
the parser and no entry in the log.  The section just goes back to a flat fill,
which looks exactly like the declaration never being written.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_header_gradient.py

Every row of the header is sampled, because the bands under test are 1px tall and
a sample at y=6 misses them.  The ``two-stop integer`` row is the control: it
shows the mechanism works, so the flat results below it are the parser's doing
rather than a missing stylesheet.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("hdg-")

BASE = "border: none; border-top: 1px solid #9e9a91; border-bottom: 1px solid #9e9a91; padding: 5px 8px;"
CASES = (
    ("flat", f"background: #eef0f2; {BASE}"),
    ("two-stop integer", f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff0000, stop:1 #0000ff); {BASE}"),
    (
        "fractional stops",
        f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff0000,"
        f" stop:0.0303 #00ff00, stop:0.9697 #00ff00, stop:1 #0000ff); {BASE}",
    ),
    (
        "percent stops",
        f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff0000,"
        f" stop:3% #00ff00, stop:97% #00ff00, stop:100% #0000ff); {BASE}",
    ),
    (
        "integer stops 0/1/1/2",
        f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff0000,"
        f" stop:1 #00ff00, stop:32 #00ff00, stop:33 #0000ff); {BASE}",
    ),
    (
        "app values",
        f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #eeebe7,"
        f" stop:0.0303 #eef0f2, stop:0.9697 #eef0f2, stop:1 #cfcdc8); {BASE}",
    ),
)


def runs(colors: list[str], first: int) -> str:
    out, cur = [], None
    for offset, colour in enumerate(colors):
        y = first + offset
        if cur and cur[2] == colour:
            runs_out = (cur[0], y, colour)
            out[-1] = runs_out
            cur = runs_out
        else:
            cur = (y, y, colour)
            out.append(cur)
    return " ".join(f"{a}-{b}:{c}" for a, b, c in out)


def main() -> int:
    from PySide6.QtWidgets import QApplication, QTableWidget

    app = QApplication([])
    for name, css in CASES:
        table = QTableWidget(3, 2)
        table.setHorizontalHeaderLabels(["a", "b"])
        table.horizontalHeader().setDefaultSectionSize(120)
        table.setStyleSheet(f"QHeaderView::section {{ {css} }}")
        table.resize(260, 200)
        table.show()
        for _ in range(6):
            app.processEvents()
        image = table.grab().toImage()
        height = table.horizontalHeader().height()
        column = [image.pixelColor(60, y).name() for y in range(height)]
        print(f"{name:<20} header={height}px  {runs(column, 0)}")
        table.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
