"""Reproduce the taskbar-toggle bug: click the app's taskbar button while the
window is normal and foreground, and see whether Windows minimizes it.

The acceptance harness only ever clicked the taskbar button when the window was
*already minimized* (the restore path).  This covers the other half of the
standard taskbar contract:

    window foreground + click its taskbar button  ->  minimize
    window minimized  + click its taskbar button  ->  restore

It also reports the style bits, because the Shell decides whether a window may
be minimized from its style (``WS_MINIMIZEBOX`` / ``WS_SYSMENU``) as much as from
its current state.

Usage:
    python diag_taskbar_toggle.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import grab  # noqa: E402
import winapi as W  # noqa: E402
from accept_packaged_exe import (  # noqa: E402
    TASKBAR_SCAN,
    InputUnavailable,
    all_visible_windows,
    app_button,
    bbox_of,
    changed_runs,
    click_taskbar_bbox,
    describe_runs,
    ensure_foreground,
    find_main_window,
    process_alive,
    wait_for_input_injection,
)

OUT_DIR = os.path.join(HERE, "out")
EXE = os.path.join(ROOT, "dist", "CodexConfigTool.exe")


def style_report(hwnd) -> dict:
    style = W.get_style(hwnd)
    ex_style = W.get_ex_style(hwnd)
    return {
        "style": hex(style),
        "ex_style": hex(ex_style),
        "WS_POPUP": bool(style & W.WS_POPUP),
        "WS_CAPTION": bool(style & W.WS_CAPTION),
        "WS_SYSMENU": bool(style & W.WS_SYSMENU),
        "WS_MINIMIZEBOX": bool(style & W.WS_MINIMIZEBOX),
        "WS_MAXIMIZEBOX": bool(style & W.WS_MAXIMIZEBOX),
        "WS_THICKFRAME": bool(style & W.WS_THICKFRAME),
        "WS_EX_APPWINDOW": bool(ex_style & W.WS_EX_APPWINDOW),
        "WS_EX_TOOLWINDOW": bool(ex_style & W.WS_EX_TOOLWINDOW),
        "has_owner": W.has_owner(hwnd),
        "would_appear_in_taskbar": W.would_appear_in_taskbar(hwnd),
    }


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    injectable, detail = wait_for_input_injection(120.0)
    if not injectable:
        print("ENVIRONMENT input injection unavailable: " + detail)
        return 3

    pre = set(all_visible_windows())
    process = subprocess.Popen([EXE], cwd=ROOT)
    hwnd, pid = find_main_window(pre)
    if not hwnd:
        print("main window not found")
        return 2
    time.sleep(2.5)
    print(f"window {hwnd:#x} pid={pid}")
    print("styles " + json.dumps(style_report(hwnd), ensure_ascii=False))

    notes: list[str] = []
    result: dict = {}

    try:
        # ---- baseline strips with the window normal AND foreground ----
        ensure_foreground(hwnd, notes, "normal baseline")
        normal_strip = os.path.join(OUT_DIR, "toggle-normal-taskbar.png")
        grab.grab_taskbar_strip().save(normal_strip)

        before = W.window_rect(hwnd)
        print(f"before click: iconic={W.is_iconic(hwnd)} rect={before}")

        # ---- click our own taskbar button while the window is normal ----
        minimized_strip = os.path.join(OUT_DIR, "toggle-minimized-taskbar.png")
        runs, button, deltas = [], None, {}
        ok = False
        # First find the button: minimize through the app's own button so we have
        # a known-good "minimized" reference to diff against, then restore.
        from accept_packaged_exe import click_app, MINIMIZE_BUTTON_OFFSET

        TITLE_BAR_HEIGHT = 38
        click_app(
            hwnd,
            before[0] + before[2] - MINIMIZE_BUTTON_OFFSET,
            before[1] + TITLE_BAR_HEIGHT // 2,
            "prime minimize",
            notes,
        )
        time.sleep(1.5)
        primed_minimized = W.is_iconic(hwnd)
        print(f"priming minimize via the custom button -> iconic={primed_minimized}")
        grab.grab_taskbar_strip().save(minimized_strip)
        runs = changed_runs(minimized_strip, normal_strip, TASKBAR_SCAN)
        button, deltas = app_button(runs, normal_strip, minimized_strip)
        print(f"button runs: {describe_runs(runs)}  deltas {deltas}")
        result["button"] = list(bbox_of(button)) if button else None

        if not button:
            print("could not locate the taskbar button; aborting")
            return 1

        # restore via the taskbar button (the path that is known to work)
        W.restore_window(hwnd)
        time.sleep(1.2)
        ensure_foreground(hwnd, notes, "restored foreground")
        time.sleep(0.4)
        print(f"restored: iconic={W.is_iconic(hwnd)} foreground={W.foreground_hwnd() == hwnd}")

        # ---- the actual test: click the taskbar button while normal ----
        bbox = bbox_of(button)
        on_taskbar = click_taskbar_bbox(bbox, notes, "toggle click (window normal)")
        time.sleep(1.8)
        after_iconic = W.is_iconic(hwnd)
        print(
            f"AFTER clicking our taskbar button while normal: "
            f"iconic={after_iconic}  (click landed on taskbar: {on_taskbar})"
        )
        result["click_while_normal_minimized"] = after_iconic

        # ---- second click should restore again ----
        click_taskbar_bbox(bbox, notes, "toggle click 2 (window minimized)")
        time.sleep(1.8)
        second_iconic = W.is_iconic(hwnd)
        print(f"AFTER a second click: iconic={second_iconic}")
        result["second_click_restored"] = not second_iconic

        # ---- for contrast: does the Shell's own SC_MINIMIZE work? ----
        if not after_iconic:
            W.minimize_window(hwnd)
            time.sleep(1.2)
            print(f"contrast: Win32 ShowWindow(SW_MINIMIZE) -> iconic={W.is_iconic(hwnd)}")
            result["showwindow_minimize_works"] = W.is_iconic(hwnd)
            W.restore_window(hwnd)
            time.sleep(0.8)

        result["notes"] = notes
        result["alive"] = process_alive(pid)
        print("RESULT " + json.dumps(result, ensure_ascii=False))
        verdict = (
            "PASS"
            if result.get("click_while_normal_minimized") and result.get("second_click_restored")
            else "REPRODUCED"
        )
        print("SUMMARY " + json.dumps({"verdict": verdict, **result}, ensure_ascii=False))
        return 0 if verdict == "PASS" else 1
    except InputUnavailable as error:
        print(f"ENVIRONMENT input injection lost mid-run: {error}")
        return 3
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
