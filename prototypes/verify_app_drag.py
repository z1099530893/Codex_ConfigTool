"""Simulate a real mouse drag on the custom title bar of the real application.

Confirms that dragging the black title bar moves the window without tearing,
fragmenting or changing the 820x500 size - and that the window is still a single
frame-less window afterwards.

Usage:
    python verify_app_drag.py
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import grab  # noqa: E402
import winapi as W  # noqa: E402

import codex_config_tool as app_module  # noqa: E402

OUT_DIR = os.path.join(HERE, "out")
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    user32 = ctypes.windll.user32
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    user32.SetCursorPos.restype = ctypes.c_bool
    user32.mouse_event.argtypes = (
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    )

    app_module.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    app_module.CodexConfigApp.check_for_updates_on_startup = lambda self: None
    app_module.CodexConfigApp._load_initial_path = lambda self: None

    # Instrument the real drag handlers so we can tell whether the synthetic
    # mouse events actually reach them.
    trace: list[str] = []
    original_start = app_module.CodexConfigApp._start_window_move
    original_move = app_module.CodexConfigApp._move_window
    original_apply = app_module.CodexConfigApp._apply_window_move
    original_stop = app_module.CodexConfigApp._stop_window_move

    def start(self, event):
        trace.append(f"start {event.x_root},{event.y_root}")
        return original_start(self, event)

    def move(self, event):
        trace.append(f"move {event.x_root},{event.y_root}")
        return original_move(self, event)

    def apply(self):
        trace.append("apply")
        return original_apply(self)

    def stop(self, event=None):
        trace.append("stop")
        return original_stop(self, event)

    app_module.CodexConfigApp._start_window_move = start
    app_module.CodexConfigApp._move_window = move
    app_module.CodexConfigApp._apply_window_move = apply
    app_module.CodexConfigApp._stop_window_move = stop

    app = app_module.CodexConfigApp()
    report: dict = {"steps": []}
    original_cursor = ctypes.wintypes.POINT()

    def cursor_save() -> None:
        user32.GetCursorPos(ctypes.byref(original_cursor))

    def drag(start_x: int, start_y: int, dx: int, dy: int) -> None:
        user32.SetCursorPos(start_x, start_y)
        app.update()
        time.sleep(0.15)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
        app.update()
        time.sleep(0.15)
        steps = 14
        for index in range(1, steps + 1):
            user32.SetCursorPos(start_x + dx * index // steps, start_y + dy * index // steps)
            app.update()
            time.sleep(0.03)
        time.sleep(0.2)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
        app.update()
        time.sleep(0.35)

    def run() -> None:
        cursor_save()
        hwnd = app._window_handle()
        report["hwnd"] = hex(hwnd)
        report["setup"] = W.describe(hwnd)

        app.lift()
        app.focus_force()
        W.user32.SetForegroundWindow(hwnd)
        app.update()
        time.sleep(0.4)

        try:
            for index, (dx, dy) in enumerate(((180, 90), (-260, 140), (120, -200), (0, 0)), start=1):
                before = W.window_rect(hwnd)
                # Grab the black title bar (38 px tall) away from the buttons.
                start_x = before[0] + 300
                start_y = before[1] + 19
                trace.clear()
                drag(start_x, start_y, dx, dy)
                after = W.window_rect(hwnd)
                frame = W.frame_thickness(hwnd)
                client = W.client_rect(hwnd)
                shot = os.path.join(OUT_DIR, f"drag{index}-win.png")
                try:
                    grab.grab_window(hwnd, margin=30).save(shot)
                except Exception as error:  # noqa: BLE001
                    shot = repr(error)
                step = {
                    "drag": index,
                    "requested": [dx, dy],
                    "moved": [after[0] - before[0], after[1] - before[1]],
                    "client": list(client),
                    "frame": list(frame),
                    "has_caption": bool(W.get_style(hwnd) & W.WS_CAPTION),
                    "iconic": W.is_iconic(hwnd),
                    "visible": W.is_visible(hwnd),
                    "screenshot": shot,
                    "handler_trace": list(trace),
                }
                report["steps"].append(step)
                print("[drag] " + json.dumps(step, ensure_ascii=False))
        finally:
            user32.SetCursorPos(original_cursor.x, original_cursor.y)

        size_ok = all(s["client"] == [app_module.WINDOW_WIDTH, app_module.WINDOW_HEIGHT] for s in report["steps"])
        frame_ok = all(not s["frame"][1] for s in report["steps"])
        report["size_stable"] = size_ok
        report["frame_clean"] = frame_ok

        path = os.path.join(OUT_DIR, "app-drag-report.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print("REPORT " + path)
        print("SUMMARY " + json.dumps({"size_stable": size_ok, "frame_clean": frame_ok}))
        app.quit()
        app.destroy()

    app.after(900, run)
    app.after(90_000, lambda: (app.quit(), app.destroy()))
    try:
        app.mainloop()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
