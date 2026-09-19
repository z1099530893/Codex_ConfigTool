"""Dump the drop-down arrow's pixels as ASCII, with no layout guesswork.

Screen grabs depend on window position and DPI, and comparing two screenshots by
eye is how the port shipped with the wrong arrow in the first place.  This
renders the arrow at its own size and prints it as a character grid, so the Tk
canvas and the Qt widget can be compared cell by cell::

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_arrow_pixels.py --framework tk
    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_arrow_pixels.py --framework qt

Tk's canvas cannot be asked to re-render itself offscreen, so it is grabbed from
the screen - but only after the probe has located the canvas widget and asserted
its size, which removes the two things that made a screen grab unreliable.
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

ROOT, CONFIG_DIR = sandbox_env.isolate("arrow-px-")

# ``#f7f8f9`` field, ``#a8adb2`` edge, ``#59616d`` chevron, ``+`` anything else.
LEGEND = {
    (247, 248, 249): ".",
    (168, 173, 178): "|",
    (89, 97, 109): "#",
}


def render(get_pixel, width: int, height: int, label: str) -> None:
    print(f"  {label}: {width}x{height}")
    print("       " + "".join(str(x % 10) for x in range(width)))
    for y in range(height):
        row = "".join(LEGEND.get(get_pixel(x, y), "+") for x in range(width))
        print(f"  {y:3d}  {row}")


def open_tk_profile_editor():
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

    def pump(seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            app.update_idletasks()
            app.update()
            time.sleep(0.01)

    pump(1.0)
    before = set(app.winfo_children())
    app._show_profile_editor()
    pump(0.9)
    opened = [w for w in app.winfo_children() if w not in before]
    if not opened:
        raise SystemExit("tk: no profile editor appeared")
    dialog = opened[-1]

    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    combo = next((w for w in walk(dialog) if isinstance(w, ttk.Combobox)), None)
    arrow = next(
        (
            w
            for w in walk(dialog)
            if isinstance(w, tk.Canvas)
            and int(w.winfo_width()) == 28
            and int(w.winfo_height()) == 29
        ),
        None,
    )
    if combo is None or arrow is None:
        raise SystemExit("tk: combobox or arrow canvas not found")
    return app, dialog, combo, arrow


def run_tk() -> int:
    from PIL import ImageGrab

    app, dialog, combo, arrow = open_tk_profile_editor()
    print("tk:")
    print(
        f"  combo {combo.winfo_width()}x{combo.winfo_height()}, "
        f"arrow at ({arrow.winfo_rootx() - combo.winfo_rootx()}, "
        f"{arrow.winfo_rooty() - combo.winfo_rooty()}) bg={arrow.cget('bg')}"
    )
    box = (
        arrow.winfo_rootx(),
        arrow.winfo_rooty(),
        arrow.winfo_rootx() + 28,
        arrow.winfo_rooty() + 29,
    )
    image = ImageGrab.grab(bbox=box)
    render(
        lambda x, y: image.getpixel((x, y))[:3],
        image.width,
        image.height,
        "arrow canvas pixels",
    )
    dialog.destroy()
    app.destroy()
    return 0


def run_qt() -> int:
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
    print("qt:")
    print(
        f"  combo {combo.width()}x{combo.height()}, "
        f"arrow at {combo.arrow.geometry().getRect()[0:2]}"
    )
    image = combo.arrow.grab().toImage()
    render(
        lambda x, y: (
            image.pixelColor(x, y).red(),
            image.pixelColor(x, y).green(),
            image.pixelColor(x, y).blue(),
        ),
        image.width(),
        image.height(),
        "arrow widget pixels",
    )

    # The whole field's right-hand end, including the arrow child: this is the
    # region the native bevel used to occupy, so it is where a leftover white
    # top border or #525353 triangle would still show.
    TAIL = 48
    field = combo.grab().toImage()
    print(f"  field's last {TAIL}px (includes the arrow child):")
    render(
        lambda x, y: (
            field.pixelColor(field.width() - TAIL + x, y).red(),
            field.pixelColor(field.width() - TAIL + x, y).green(),
            field.pixelColor(field.width() - TAIL + x, y).blue(),
        ),
        TAIL,
        field.height(),
        "field tail",
    )

    dialog.close()
    window.close()
    pump(0.2)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=("tk", "qt"), required=True)
    args = parser.parse_args()
    return run_tk() if args.framework == "tk" else run_qt()


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)

