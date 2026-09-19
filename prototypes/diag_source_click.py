"""Source-level diagnostic: what happens when the custom minimize button is clicked.

Unlike ``verify_app_window.py`` (which calls ``_minimize_window`` directly), this
performs a real synthetic mouse click on the actual canvas widget, so it can tell
"the click never reached the button" apart from "the button ran but the window
did not stay minimized".

It also reports the true on-screen rectangle of every title-bar button, measured
from the live widget tree, so the hard-coded ``right - 63`` offset can be checked.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import winapi as W  # noqa: E402

import codex_config_tool as app_module  # noqa: E402

TITLE_BAR_HEIGHT = 38
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

user32 = ctypes.windll.user32
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.mouse_event.argtypes = (
    ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p
)
user32.WindowFromPoint.argtypes = (wintypes.POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, ctypes.c_uint)
user32.GetAncestor.restype = wintypes.HWND

LOG: list[str] = []
BUTTONS: dict[str, object] = {}


def log(message: str) -> None:
    LOG.append(message)
    print(message, flush=True)


def click(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.09)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)


def under_point(x: int, y: int) -> str:
    hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
    if not hwnd:
        return "none"
    root = user32.GetAncestor(hwnd, 2) or hwnd
    return f"hwnd={int(hwnd):#x} class={W.class_name(hwnd)!r} root={int(root):#x}"


def main() -> int:
    app_module.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    app_module.CodexConfigApp.check_for_updates_on_startup = lambda self: None
    app_module.CodexConfigApp._load_initial_path = lambda self: None

    # Capture the real canvases so their geometry can be measured.
    original_factory = app_module.CodexConfigApp._title_icon_button

    def spy(self, parent, kind, command):
        canvas = original_factory(self, parent, kind, command)
        BUTTONS[kind] = canvas
        return canvas

    app_module.CodexConfigApp._title_icon_button = spy

    # Instrument the lifecycle without changing behaviour.
    original_minimize = app_module.minimize_toplevel_window
    original_window_handle = app_module.CodexConfigApp._window_handle

    def traced_minimize(hwnd):
        result = original_minimize(hwnd)
        log(f"    [minimize_toplevel_window] hwnd={hwnd:#x} -> {result}")
        return result

    app_module.minimize_toplevel_window = traced_minimize

    def traced_handle(self):
        hwnd = original_window_handle(self)
        log(f"    [_window_handle] -> {hwnd:#x}")
        return hwnd

    app_module.CodexConfigApp._window_handle = traced_handle

    app = app_module.CodexConfigApp()
    original_minimize_method = app._minimize_window

    def traced_minimize_method():
        log("    [_minimize_window] CALLED")
        original_minimize_method()

    app._minimize_window = traced_minimize_method

    state = {"hwnd": 0, "done": False}

    def finish(code: int = 0) -> None:
        if state["done"]:
            return
        state["done"] = True
        path = os.path.join(HERE, "out", "diag-source-click.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"log": LOG}, handle, ensure_ascii=False, indent=2)
        print("LOG " + path)
        try:
            app.quit()
            app.destroy()
        except Exception:  # noqa: BLE001
            pass

    def setup() -> None:
        state["hwnd"] = app._window_handle()
        log(f"[setup] {W.describe(state['hwnd'])}")
        log(f"[setup] taskbar_button_ready={app._taskbar_button_ready}")
        for kind, canvas in BUTTONS.items():
            log(
                f"[button] {kind:9s} rootx={canvas.winfo_rootx()} rooty={canvas.winfo_rooty()}"
                f" w={canvas.winfo_width()} h={canvas.winfo_height()}"
                f" mapped={bool(canvas.winfo_ismapped())} manager={canvas.winfo_manager()}"
            )
        app.after(400, probe)

    def probe() -> None:
        minimize = BUTTONS["minimize"]
        x = minimize.winfo_rootx() + minimize.winfo_width() // 2
        y = minimize.winfo_rooty() + minimize.winfo_height() // 2
        left, top, width, _height = W.window_rect(state["hwnd"])
        log(f"[probe] minimize canvas centre = ({x}, {y})")
        log(f"[probe] hard-coded offset point  = ({left + width - 63}, {top + TITLE_BAR_HEIGHT // 2})")
        log(f"[probe] winfo_containing({x}, {y}) = {app.winfo_containing(x, y)}")
        log(f"[probe] under_point = {under_point(x, y)}")
        log(f"[probe] foreground = {user32.GetForegroundWindow() or 0:#x} (ours={state['hwnd']:#x})")
        log(f"[probe] before click: iconic={W.is_iconic(state['hwnd'])} rect={W.window_rect(state['hwnd'])}")
        log("[probe] CLICK")
        click(x, y)
        app.after(1200, after_click)

    def after_click() -> None:
        hwnd = state["hwnd"]
        log(f"[after ] iconic={W.is_iconic(hwnd)} rect={W.window_rect(hwnd)}")
        log(f"[after ] client={W.client_rect(hwnd)} frame={W.frame_thickness(hwnd)}")
        log(f"[after ] foreground = {user32.GetForegroundWindow() or 0:#x} (ours={hwnd:#x})")
        log(f"[after ] tk state={app.state()}")
        if W.is_iconic(hwnd):
            log("[after ] minimized as expected; restoring for a second attempt")
            W.restore_window(hwnd)
            app.after(900, second)
        else:
            log("[after ] NOT minimized -> second attempt from a fresh foreground")
            second()

    def second() -> None:
        hwnd = state["hwnd"]
        minimize = BUTTONS["minimize"]
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.4)
        x = minimize.winfo_rootx() + minimize.winfo_width() // 2
        y = minimize.winfo_rooty() + minimize.winfo_height() // 2
        log(f"[second] foreground={user32.GetForegroundWindow() or 0:#x} clicking ({x}, {y})")
        click(x, y)
        app.after(1200, final)

    def final() -> None:
        hwnd = state["hwnd"]
        log(f"[final ] iconic={W.is_iconic(hwnd)} rect={W.window_rect(hwnd)} tk state={app.state()}")
        if W.is_iconic(hwnd):
            W.restore_window(hwnd)
        app.after(500, lambda: finish())

    app.after(800, setup)
    app.after(60_000, lambda: finish())
    try:
        app.mainloop()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
