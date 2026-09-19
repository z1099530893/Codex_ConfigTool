"""Which QHeaderView resize-mode combination reproduces ttk's column widths?

Tk configures the two profile columns as ``width=225`` and ``width=330`` (555 total) inside a
608px-wide ``Treeview``.  ttk's ``stretch`` defaults to true on *every* column, so the 53px of slack
is split between them and the first column ends up ~251px wide.  Qt's port gives column 0 a fixed
225 (``Interactive``) and lets column 1 absorb all the slack (``Stretch``), which is a different
*rule*, not just a different number - it would stay 225 however wide the window got.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_column_widths.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("col-width-")

from PySide6.QtWidgets import QHeaderView  # noqa: E402

import codex_config_qt as ui  # noqa: E402

# Tk: treeview is 608px wide, columns configured 225 + 330 = 555, slack 53 split two ways.
TK_TOTAL = 608
TK_COL0 = 225
TK_COL1 = 330

VARIANTS = {
    "interactive 225 + stretch (current)": ("interactive", 225),
    "stretch + stretch": ("stretch", 225),
    "interactive 225/330 + stretchLast": ("stretchlast", 225),
    "interactive 225/330, no stretch": ("fixed", 225),
}


def apply(header, mode: str) -> None:
    header.setStretchLastSection(False)
    if mode == "stretch":
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    elif mode == "stretchlast":
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
    elif mode == "fixed":
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    else:
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)


def main() -> int:
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

    def pump(seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)

    pump(0.8)
    window.show_page("profiles")
    pump(0.8)

    table = window.profile_table
    header = table.horizontalHeader()
    print(f"tk target: view {TK_TOTAL}px, col0 {TK_COL0} -> stretched to ~{TK_COL0 + (TK_TOTAL - TK_COL0 - TK_COL1) // 2}")
    print(f"qt view is {table.width()}px wide\n")
    for name, (mode, width) in VARIANTS.items():
        apply(header, mode)
        header.resizeSection(0, width)
        header.resizeSection(1, TK_COL1)
        pump(0.4)
        col0 = header.sectionSize(0)
        col1 = header.sectionSize(1)
        print(
            f"  {name:36s} col0={col0:4d} col1={col1:4d} "
            f"total={col0 + col1:4d}  (view {table.width()})"
        )

    window.close()
    pump(0.2)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
