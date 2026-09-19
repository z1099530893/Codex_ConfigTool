"""Compare the 启动默认模型 drop-down arrow between the Tk and Qt front ends.

The Qt port dropped the hand-drawn arrow and let ``QComboBox`` draw its own,
which renders as a beveled native button (white top border, ``#525353`` bottom
border, filled triangle).  The user reported it as "跟之前的也不一样了".  This
probe puts the two side by side at 4x and, more usefully, samples the pixels so
the comparison does not depend on anyone's eyes.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_combo_arrow.py --framework tk
    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_combo_arrow.py --framework qt

Writes ``out/combo-<framework>.png`` (4x zoom of the field's right-hand end) and
prints the geometry and the sampled colours.  State is redirected, so this
cannot touch the user's real configuration.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("combo-arrow-")

from PIL import Image, ImageGrab  # noqa: E402

OUT = HERE / "out"
ZOOM = 4
# The arrow zone Tk places inside the field, in the field's own coordinates.
ZONE = (28, 29)


def crop_zoom(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    return image.crop(box).resize(
        ((box[2] - box[0]) * ZOOM, (box[3] - box[1]) * ZOOM), Image.NEAREST
    )


def describe(image: Image.Image, label: str) -> None:
    """Print the distinct colours down the arrow zone's centre row and column."""
    width, height = image.size
    print(f"  {label}: {width}x{height}")
    row = [image.getpixel((x, height // 2)) for x in range(width)]
    print(f"    centre row : {row}")
    column = [image.getpixel((width // 2, y)) for y in range(height)]
    print(f"    centre col : {column}")
    colours = sorted({p for p in row + column}, key=lambda p: sum(p[:3]))
    print(f"    palette    : {['#%02x%02x%02x' % p[:3] for p in colours]}")


def run_tk() -> int:
    import tkinter as tk
    from tkinter import ttk

    import codex_config_tool as core

    core.CodexConfigApp._load_initial_path = lambda self: (
        self.path_var.set(str(CONFIG_DIR)),
        self.load_path(CONFIG_DIR),
    )
    core.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    core.CodexConfigApp.check_for_updates_on_startup = lambda self: None

    app = core.CodexConfigApp()
    app.deiconify()
    deadline = time.time() + 1.0
    while time.time() < deadline:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)

    before = set(app.winfo_children())
    app._show_profile_editor()
    deadline = time.time() + 0.9
    while time.time() < deadline:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)
    opened = [w for w in app.winfo_children() if w not in before]
    if not opened:
        print("tk: no profile editor appeared")
        return 1
    dialog = opened[-1]

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    combo = next(
        (w for w in walk(dialog) if isinstance(w, ttk.Combobox)),
        None,
    )
    if combo is None:
        print("tk: no combobox found")
        return 1
    arrow = next(
        (
            w
            for w in walk(dialog)
            if isinstance(w, tk.Canvas)
            and int(w.winfo_width()) == ZONE[0]
            and int(w.winfo_height()) == ZONE[1]
        ),
        None,
    )
    print("tk:")
    print(
        f"  combo  : x={combo.winfo_rootx()} y={combo.winfo_rooty()} "
        f"{combo.winfo_width()}x{combo.winfo_height()}"
    )
    if arrow is not None:
        print(
            f"  arrow  : x={arrow.winfo_rootx()} y={arrow.winfo_rooty()} "
            f"{arrow.winfo_width()}x{arrow.winfo_height()} bg={arrow.cget('bg')}"
        )
        zone = (
            arrow.winfo_rootx(),
            arrow.winfo_rooty(),
            arrow.winfo_rootx() + arrow.winfo_width(),
            arrow.winfo_rooty() + arrow.winfo_height(),
        )
    else:
        print("  arrow  : not found, falling back to the field's right end")
        zone = (
            combo.winfo_rootx() + combo.winfo_width() - ZONE[0],
            combo.winfo_rooty(),
            combo.winfo_rootx() + combo.winfo_width(),
            combo.winfo_rooty() + combo.winfo_height(),
        )
    shot = ImageGrab.grab(bbox=zone)
    shot.save(OUT / "combo-tk-zone.png")
    describe(shot, "zone")

    # The whole field, for context.
    field = (
        combo.winfo_rootx(),
        combo.winfo_rooty(),
        combo.winfo_rootx() + combo.winfo_width(),
        combo.winfo_rooty() + combo.winfo_height(),
    )
    crop_zoom(ImageGrab.grab(bbox=field), (0, 0, field[2] - field[0], field[3] - field[1])).save(
        OUT / "combo-tk.png"
    )
    print(f"  saved out/combo-tk.png ({field[2] - field[0]}x{field[3] - field[1]}, {ZOOM}x)")

    dialog.destroy()
    app.destroy()
    return 0


def run_qt() -> int:
    from PySide6.QtCore import QPoint

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
    window.activateWindow()

    def pump(seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)

    pump(0.8)
    dialog = ui.ProfileEditorDialog(window, None)
    dialog.show()
    dialog.raise_()
    pump(0.8)

    combo = dialog.model_combo
    origin = combo.mapToGlobal(QPoint(0, 0))
    print("qt:")
    print(
        f"  combo  : x={origin.x()} y={origin.y()} "
        f"{combo.width()}x{combo.height()}"
    )
    arrow = combo.arrow
    arrow_origin = arrow.mapToGlobal(QPoint(0, 0))
    print(
        f"  arrow  : x={arrow_origin.x()} y={arrow_origin.y()} "
        f"{arrow.width()}x{arrow.height()} visible={arrow.isVisible()}"
    )

    zone = (
        arrow_origin.x(),
        arrow_origin.y(),
        arrow_origin.x() + arrow.width(),
        arrow_origin.y() + arrow.height(),
    )
    shot = ImageGrab.grab(bbox=zone)
    shot.save(OUT / "combo-qt-zone.png")
    describe(shot, "zone")

    field = (
        origin.x(),
        origin.y(),
        origin.x() + combo.width(),
        origin.y() + combo.height(),
    )
    crop_zoom(ImageGrab.grab(bbox=field), (0, 0, field[2] - field[0], field[3] - field[1])).save(
        OUT / "combo-qt.png"
    )
    print(f"  saved out/combo-qt.png ({field[2] - field[0]}x{field[3] - field[1]}, {ZOOM}x)")

    dialog.close()
    window.close()
    pump(0.2)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=("tk", "qt"), required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    return run_tk() if args.framework == "tk" else run_qt()


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
