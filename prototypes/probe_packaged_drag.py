"""Does a preliminary click break the title-bar drag on a packaged Qt window?

`accept_packaged_exe.py` calls `click_app()` - which performs a **complete click**
(press + release) - at the drag's start point, and only then begins the drag's own
press. On this window a press on the title strip calls `startSystemMove()`, which
hands the drag to the OS's modal `SC_MOVE` loop. The hypothesis is that the
preliminary click enters that loop and leaves the window in a state where the
following press no longer starts a move, so the drag reports `moved [0, 0]` while
the input channel is perfectly healthy.

This probe isolates that single variable on the **packaged** EXE: one drag with the
preliminary click, one without, same window, same session.

    APPDATA=... python probe_packaged_drag.py --exe dist/CodexConfigTool-Qt.exe
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import grab  # noqa: E402
import winapi as W  # noqa: E402
import accept_packaged_exe as A  # noqa: E402

user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
TITLE_BAR_HEIGHT = 38
STEPS = 12


def drag(hwnd: int, dx: int, dy: int, *, preliminary_click: bool, notes: list[str],
         after_down: float = 0.20, use_move_cursor: bool = False,
         before_down: float = 0.20, fg_before: bool = False) -> dict:
    before = W.window_rect(hwnd)
    x = before[0] + 300
    y = before[1] + TITLE_BAR_HEIGHT // 2

    # fg_before reproduces drag_window's own ordering: make_foreground runs
    # immediately before the press, with no settling gap.
    if fg_before:
        A.ensure_foreground(hwnd, notes, "fg-immediately-before")

    if preliminary_click:
        # Exactly what click_app does: ensure_clickable + a full click.
        ok, detail = W.ensure_clickable(hwnd, x, y)
        notes.append(f"preliminary ensure_clickable @({x},{y}): {detail}")
        A.click(x, y)
        time.sleep(0.3)
    else:
        ok, detail = W.ensure_clickable(hwnd, x, y)
        notes.append(f"no preliminary click; ensure_clickable @({x},{y}): {detail}")

    user32.SetCursorPos(x, y)
    time.sleep(before_down)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(after_down)
    for index in range(1, STEPS + 1):
        step_x, step_y = x + dx * index // STEPS, y + dy * index // STEPS
        if use_move_cursor:
            A.move_cursor(step_x, step_y)
            time.sleep(0.03)
        else:
            user32.SetCursorPos(step_x, step_y)
            time.sleep(0.035)
    tx, ty = x + dx, y + dy
    user32.SetCursorPos(tx + 1, ty + 1)
    time.sleep(0.08)
    user32.SetCursorPos(tx, ty)
    time.sleep(0.10)
    time.sleep(0.25)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.40)

    after = W.window_rect(hwnd)
    return {
        "preliminary_click": preliminary_click,
        "fg_before": fg_before,
        "before_down": before_down,
        "after_down": after_down,
        "use_move_cursor": use_move_cursor,
        "requested": [dx, dy],
        "moved": [after[0] - before[0], after[1] - before[1]],
        "client": list(W.client_rect(hwnd)),
        "frame": list(W.frame_thickness(hwnd)),
    }


def drag_window_copy(hwnd: int, dx: int, dy: int, notes: list[str], label: str) -> dict:
    """A verbatim copy of accept_packaged_exe.drag_window's body.

    Run next to the original: if both fail, the body is at fault and can be
    bisected; if only the original fails, the difference is in its module context
    (which global it resolves, which user32 handle it uses) rather than the steps.
    """
    before = W.window_rect(hwnd)
    foreground = A.ensure_foreground(hwnd, notes, label)
    click_x = before[0] + 300
    click_y = before[1] + TITLE_BAR_HEIGHT // 2
    pressed = A.click_app(hwnd, click_x, click_y, f"{label} press", notes)
    user32.SetCursorPos(click_x, click_y)
    time.sleep(0.15)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.12)
    for step in range(1, 13):
        A.move_cursor(click_x + dx * step // 12, click_y + dy * step // 12)
        time.sleep(0.03)
    time.sleep(0.15)
    target_x, target_y = click_x + dx, click_y + dy
    user32.SetCursorPos(target_x + 1, target_y + 1)
    time.sleep(0.08)
    user32.SetCursorPos(target_x, target_y)
    time.sleep(0.10)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.4)
    after = W.window_rect(hwnd)
    return {
        "label": label,
        "pressed": pressed,
        "foreground": foreground,
        "requested": [dx, dy],
        "moved": [after[0] - before[0], after[1] - before[1]],
        "client": list(W.client_rect(hwnd)),
        "frame": list(W.frame_thickness(hwnd)),
    }


def drag_window_noclick(hwnd: int, dx: int, dy: int, notes: list[str], label: str) -> dict:
    """drag_window's body with the preliminary *click* removed.

    `click_app` performs a complete press+release at the drag's start point. On this
    window a press on the title strip calls `startSystemMove()`, which hands control
    to the OS's modal SC_MOVE loop - so the preliminary click enters that loop and
    releases immediately, and the drag's own press arrives while the loop is still
    winding down. A drag needs no preliminary click anyway: its own press is the
    press, and `ensure_clickable` raises the window without clicking.
    """
    before = W.window_rect(hwnd)
    foreground = A.ensure_foreground(hwnd, notes, label)
    click_x = before[0] + 300
    click_y = before[1] + TITLE_BAR_HEIGHT // 2
    ok, detail = W.ensure_clickable(hwnd, click_x, click_y)
    notes.append(f"{label} ensure_clickable(no click) @({click_x},{click_y}): {detail}")
    user32.SetCursorPos(click_x, click_y)
    time.sleep(0.15)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.12)
    for step in range(1, 13):
        A.move_cursor(click_x + dx * step // 12, click_y + dy * step // 12)
        time.sleep(0.03)
    time.sleep(0.15)
    target_x, target_y = click_x + dx, click_y + dy
    user32.SetCursorPos(target_x + 1, target_y + 1)
    time.sleep(0.08)
    user32.SetCursorPos(target_x, target_y)
    time.sleep(0.10)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.4)
    after = W.window_rect(hwnd)
    return {
        "label": label,
        "pressed": ok,
        "foreground": foreground,
        "requested": [dx, dy],
        "moved": [after[0] - before[0], after[1] - before[1]],
        "client": list(W.client_rect(hwnd)),
        "frame": list(W.frame_thickness(hwnd)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=os.path.join(ROOT, "dist", "CodexConfigTool-Qt.exe"))
    parser.add_argument("--window-class", default="Qt")
    args = parser.parse_args()

    exe = os.path.abspath(args.exe)
    if not os.path.exists(exe):
        print("MISSING EXE " + exe)
        return 2

    notes: list[str] = []
    pre_existing = set(A.all_visible_windows())
    A.close_existing_app_windows(notes)

    process = subprocess.Popen([exe], cwd=ROOT)
    try:
        hwnd, pid = A.find_main_window(pre_existing, window_class=args.window_class)
        if not hwnd:
            print("NO WINDOW")
            return 3
        print(f"hwnd={hwnd:#x} pid={pid} class={W.class_name(hwnd)}")

        A.ensure_foreground(hwnd, notes, "initial")
        time.sleep(0.5)

        results = []

        # Three implementations, several rounds each: the harness's own function, a
        # verbatim copy of its body, and the inline technique that is known to work.
        for round_index in range(1, 4):
            for name, fn in (
                ("harness-fn", lambda: A.drag_window(hwnd, 150, 70, notes, f"r{round_index}-hfn")),
                ("body-copy", lambda: drag_window_copy(hwnd, 150, 70, notes, f"r{round_index}-copy")),
                ("no-prelim-click", lambda: drag_window_noclick(hwnd, 150, 70, notes, f"r{round_index}-noclick")),
                ("inline", lambda: drag(hwnd, 150, 70, preliminary_click=False, notes=notes)),
            ):
                A.ensure_foreground(hwnd, notes, f"round{round_index}-{name}")
                time.sleep(0.4)
                entry = fn()
                entry["variant"] = f"{name}-{round_index}"
                results.append(entry)
                if entry["moved"] != [0, 0]:
                    drag(hwnd, -entry["moved"][0], -entry["moved"][1],
                         preliminary_click=False, notes=notes)

        print()
        for entry in results:
            ok = entry["moved"] == entry["requested"]
            print(("PASS " if ok else "FAIL ") + json.dumps(entry, ensure_ascii=False))

        print()
        for prefix in ("harness-fn", "body-copy", "no-prelim-click", "inline"):
            runs = [e for e in results if e["variant"].startswith(prefix)]
            moved = sum(1 for e in runs if e["moved"] == e["requested"])
            print(f"{prefix:12s}: {moved}/{len(runs)} moved")
        return 0
    finally:
        for pid in {process.pid, locals().get("pid", 0)}:
            if pid:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )


if __name__ == "__main__":
    raise SystemExit(main())
