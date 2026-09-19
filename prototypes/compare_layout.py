"""Compare the vertical layout of one page between the Tk and the Qt front end.

Layout fidelity is the one thing a structural test cannot check: a widget can
exist, carry the right object name and be wired to the right slot while sitting
in the wrong place.  The Qt port's pages drifted from the Tk design exactly that
way - every check passed, and 官方登录 had a 200px hole above its panel.

This dumps the geometry of the widgets that matter so the two front ends can be
compared as numbers rather than eyeballed as pictures.

    "C:/Program Files/Develop/Python/python.exe" prototypes/compare_layout.py --framework tk --page current
    "C:/Program Files/Develop/Python/python.exe" prototypes/compare_layout.py --framework qt --page current

Writes ``out/layout-<framework>-<page>.json`` and prints a table sorted by y.

All persisted state is redirected, so this cannot touch the user's real config.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("layout-")

OUT = HERE / "out"

# Only the content column; the sidebar is identical in both and just adds noise.
CONTENT_LEFT = 150
PAGES = ("current", "profiles", "official", "guide", "recommended")


def _tk_text(widget) -> str:
    """The text a widget shows, however that widget happens to store it.

    Order matters.  ``ttk.Entry`` aliases ``-text`` to ``-textvariable``, so
    ``cget("text")`` hands back the Tcl variable's *name* - the dump printed
    ``PY_VAR5`` where the Qt side printed the path it holds, and the two tables
    could not be lined up.  Read the variable's value first, then ``get()``
    (which ttk entries and comboboxes use), and only then a literal ``text``.
    """
    try:
        variable = widget.cget("textvariable")
    except Exception:
        variable = ""
    if variable:
        try:
            return str(widget.getvar(variable) or "")[:40]
        except Exception:
            return ""
    getter = getattr(widget, "get", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = ""
        if value:
            return str(value)[:40]
    try:
        return str(widget.cget("text") or "")[:40]
    except Exception:
        return ""


def walk_tk(widget, ox: int, oy: int, depth: int, rows: list, max_depth: int = 14) -> None:
    try:
        cls = widget.winfo_class()
        x = widget.winfo_rootx() - ox
        y = widget.winfo_rooty() - oy
        w = widget.winfo_width()
        h = widget.winfo_height()
    except Exception:
        return
    # Unmapped widgets still report a geometry, and it is meaningless - the
    # profiles page's multi-select bar reports y=38 h=480 while hidden.  Only
    # what is on screen is worth comparing.
    if widget.winfo_ismapped():
        rows.append(
            {"depth": depth, "class": cls, "x": x, "y": y, "w": w, "h": h, "text": _tk_text(widget)}
        )
    if depth >= max_depth:
        return
    for child in widget.winfo_children():
        walk_tk(child, ox, oy, depth + 1, rows, max_depth)


def run_tk(page_key: str) -> list:
    import codex_config_tool as core

    core.CodexConfigApp._load_initial_path = lambda self: (
        self.path_var.set(str(CONFIG_DIR)),
        self.load_path(CONFIG_DIR),
    )
    core.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    core.CodexConfigApp.check_for_updates_on_startup = lambda self: None

    app = core.CodexConfigApp()
    app.deiconify()
    for _ in range(4):
        app.update_idletasks()
        app.update()
    app.show_page(page_key)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)

    rows: list = []
    # Walk only the requested page: all five are stacked at the same place, so
    # walking the whole app returns five overlapping pages and no way to tell
    # which row belongs to which.
    walk_tk(app.pages[page_key], app.winfo_rootx(), app.winfo_rooty(), 0, rows)
    app.destroy()
    return rows


def walk_qt(widget, window, depth: int, rows: list, max_depth: int = 14) -> None:
    from PySide6.QtWidgets import QWidget

    for child in widget.children():
        if not isinstance(child, QWidget):
            continue
        if not child.isVisible():
            # Same reason as the Tk side: a hidden widget's geometry is not a
            # layout decision.  The profiles page keeps its multi-select bar
            # hidden here.
            continue
        try:
            pos = child.mapTo(window, child.rect().topLeft())
            geo = child.geometry()
        except Exception:
            continue
        text = ""
        for getter in ("text", "currentText"):
            if hasattr(child, getter):
                try:
                    text = str(getattr(child, getter)())[:40]
                    break
                except Exception:
                    pass
        rows.append(
            {
                "depth": depth,
                "class": type(child).__name__,
                "name": child.objectName(),
                "x": pos.x(),
                "y": pos.y(),
                "w": geo.width(),
                "h": geo.height(),
                "text": text,
            }
        )
        if depth < max_depth:
            walk_qt(child, window, depth + 1, rows, max_depth)


def run_qt(page_key: str) -> list:
    import codex_config_qt as ui

    app = ui.create_application()
    ui.CodexConfigWindow._load_initial_path = lambda self: (
        self._set_path(CONFIG_DIR),
        self.load_path(CONFIG_DIR),
    )
    ui.CodexConfigWindow.show_onboarding_dialog = lambda self, force=False: None
    ui.CodexConfigWindow.check_for_updates_on_startup = lambda self: None

    window = ui.CodexConfigWindow()
    window.show()
    window.raise_()
    deadline = time.time() + 1.2
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    window.show_page(page_key)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)

    rows: list = []
    walk_qt(window.pages[page_key], window, 0, rows)
    window.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=("tk", "qt"), required=True)
    parser.add_argument("--page", choices=PAGES, default="current")
    parser.add_argument("--all-width", action="store_true", help="include the sidebar too")
    args = parser.parse_args()

    rows = run_tk(args.page) if args.framework == "tk" else run_qt(args.page)

    OUT.mkdir(parents=True, exist_ok=True)
    report = OUT / f"layout-{args.framework}-{args.page}.json"
    report.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    left = 0 if args.all_width else CONTENT_LEFT
    visible = [
        r
        for r in rows
        if r["x"] + r["w"] > left and r["w"] > 1 and r["h"] > 1 and r["y"] >= 0
    ]
    visible.sort(key=lambda r: (r["y"], r["x"]))
    print(f"{args.framework} / {args.page}: {len(visible)} widgets  ->  {report.name}")
    print(f"{'y':>5} {'h':>5} {'x':>5} {'w':>5}  {'depth':>5}  class / text")
    for r in visible:
        label = r.get("name") or ""
        text = r["text"]
        tail = f"{r['class']}"
        if label:
            tail += f"[{label}]"
        if text:
            tail += f"  {text!r}"
        print(f"{r['y']:>5} {r['h']:>5} {r['x']:>5} {r['w']:>5}  {r['depth']:>5}  {tail}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
