"""Save a screenshot of every page of the *shipping* Tk window.

``qt_visual_tour.py`` says what the port renders; this says what it has to match.
Layout fidelity is not something a structural test can check - a widget can be
present, correctly named and correctly wired while sitting in the wrong place -
so the only honest check is two images side by side.

Writes to ``out/tk-tour-*.png``.  All persisted state is redirected, so this
cannot touch the user's real configuration.

    "C:/Program Files/Develop/Python/python.exe" prototypes/tk_visual_tour.py

Two details worth keeping:

* Tk needs ``update_idletasks()`` *and* ``update()`` driven by hand; there is no
  event loop here, so a single call leaves geometry half-computed and the shot
  catches a layout that never existed.
* The pages are pumped for a couple of seconds before shooting, because the app
  raises a toast on first use ("已创建可编辑配置...") that overlays the bottom
  of the page.  Shooting through it makes a correct layout look broken - and
  worse, makes a *broken* layout look broken for the wrong reason.
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("tk-tour-")

from PIL import ImageGrab  # noqa: E402

import winapi  # noqa: E402

import codex_config_tool as core  # noqa: E402

OUT = HERE / "out"
PAGES = ("current", "profiles", "official", "guide", "recommended")


def pump(app, seconds: float = 0.6) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update_idletasks()
        app.update()
        time.sleep(0.01)


def shoot(app, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    app.update_idletasks()
    app.update()
    hwnd = app._window_handle()
    # window_rect returns (left, top, width, height), not a RECT.
    left, top, width, height = winapi.window_rect(hwnd)
    ImageGrab.grab(bbox=(left, top, left + width, top + height)).save(
        OUT / f"tk-tour-{name}.png"
    )
    print(f"  saved out/tk-tour-{name}.png")


def shoot_dialog(dialog, name: str) -> None:
    """Capture a Toplevel's client area.

    ``winfo_rootx``/``winfo_width`` describe the *client* area, so the shot has
    no native title bar.  That is what is wanted here: the Qt tour captures the
    frame, and comparing the two means comparing content, not chrome.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    dialog.update_idletasks()
    dialog.update()
    left, top = dialog.winfo_rootx(), dialog.winfo_rooty()
    width, height = dialog.winfo_width(), dialog.winfo_height()
    ImageGrab.grab(bbox=(left, top, left + width, top + height)).save(
        OUT / f"tk-tour-{name}.png"
    )
    print(f"  saved out/tk-tour-{name}.png  ({width}x{height})")


def main() -> int:
    core.CodexConfigApp._load_initial_path = lambda self: (
        self.path_var.set(str(CONFIG_DIR)),
        self.load_path(CONFIG_DIR),
    )
    core.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    core.CodexConfigApp.check_for_updates_on_startup = lambda self: None

    app = core.CodexConfigApp()
    app.deiconify()
    app.lift()
    pump(app, 1.0)

    print("pages:")
    for key in PAGES:
        app.show_page(key)
        # Long enough for the first-use toast to fade off the bottom of the page.
        pump(app, 2.5)
        shoot(app, key)

    print("dialogs:")
    # ``show_custom_dialog`` blocks on wait_window, so the message boxes are not
    # in this list; the rest only grab_set and return.
    dialogs = (
        ("about", lambda: app.show_about_dialog()),
        ("profile-editor", lambda: app._show_profile_editor()),
        ("onboarding", lambda: app.show_onboarding_dialog(True)),
        ("donation", lambda: app.show_donation_dialog()),
    )
    for name, factory in dialogs:
        before = set(app.winfo_children())
        factory()
        pump(app, 0.9)
        opened = [w for w in app.winfo_children() if w not in before]
        if not opened:
            print(f"  [skip] {name}: no dialog appeared")
            continue
        dialog = opened[-1]
        shoot_dialog(dialog, name)
        try:
            dialog.grab_release()
        except tk.TclError:
            pass
        dialog.destroy()
        pump(app, 0.2)

    app.destroy()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
