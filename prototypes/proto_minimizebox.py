"""Prototype: give the borderless window WS_MINIMIZEBOX so the Shell treats it as
minimizable, and check that doing so costs nothing else.

The Shell decides whether a window can be minimized from ``WS_MINIMIZEBOX``
(Raymond Chen, "Why does adding WS_MINIMIZEBOX change how my window behaves when
the user presses Win+D?").  Without it the taskbar button is activate-only, which
is exactly the reported bug: clicking the icon does not toggle minimize/restore.

``WS_MINIMIZEBOX`` requires ``WS_SYSMENU`` to be meaningful, and ``WS_SYSMENU`` is
what gives the window the system menu the taskbar jump list reads.  Neither bit
draws a frame - frames come from ``WS_CAPTION``/``WS_BORDER``/``WS_DLGFRAME``/
``WS_THICKFRAME`` - but that has to be *measured*, because the whole design
depends on the non-client frame staying ``(0, 0)`` and the client staying 820x500.

This applies the change to a running packaged executable from the outside, so the
source is untouched until the result is known good.

Usage:
    python proto_minimizebox.py
"""

from __future__ import annotations

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

import winapi as W  # noqa: E402
from accept_packaged_exe import all_visible_windows, find_main_window, process_alive  # noqa: E402
from diag_syscommand import system_menu_report  # noqa: E402

user32 = ctypes.windll.user32
WINDOW_WIDTH, WINDOW_HEIGHT = 820, 500
WM_SYSCOMMAND = 0x0112
SC_MINIMIZE = 0xF020
SC_RESTORE = 0xF120
SC_MAXIMIZE = 0xF030

user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = ctypes.c_void_p


def snapshot(hwnd) -> dict:
    style = W.get_style(hwnd)
    return {
        "style": hex(style),
        "WS_POPUP": bool(style & W.WS_POPUP),
        "WS_CAPTION": bool(style & W.WS_CAPTION),
        "WS_SYSMENU": bool(style & W.WS_SYSMENU),
        "WS_MINIMIZEBOX": bool(style & W.WS_MINIMIZEBOX),
        "WS_MAXIMIZEBOX": bool(style & W.WS_MAXIMIZEBOX),
        "frame": list(W.frame_thickness(hwnd)),
        "client": list(W.client_rect(hwnd)),
        "has_caption": bool(style & W.WS_CAPTION),
        "system_menu": system_menu_report(hwnd),
    }


def add_minimize_box(hwnd) -> None:
    """Add WS_SYSMENU|WS_MINIMIZEBOX without disturbing anything else."""
    style = W.get_style(hwnd)
    new_style = style | W.WS_SYSMENU | W.WS_MINIMIZEBOX
    W._set_long(wintypes.HWND(hwnd), W.GWL_STYLE, ctypes.c_void_p(new_style))
    # SWP_FRAMECHANGED makes the non-client area recompute; SWP_NOACTIVATE keeps
    # the window from stealing focus.  No move, no resize.
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        None,
        0,
        0,
        0,
        0,
        W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOZORDER | W.SWP_NOACTIVATE | W.SWP_FRAMECHANGED,
    )


def main() -> int:
    pre = set(all_visible_windows())
    process = subprocess.Popen([os.path.join(ROOT, "dist", "CodexConfigTool.exe")], cwd=ROOT)
    hwnd, pid = find_main_window(pre)
    if not hwnd:
        print("main window not found")
        return 2
    time.sleep(2.5)

    failures: list[str] = []
    report: dict = {"hwnd": hex(hwnd), "pid": pid}
    print(f"window {hwnd:#x} pid={pid} {W.describe(hwnd)}")

    try:
        before = snapshot(hwnd)
        report["before"] = before
        print("\nBEFORE " + json.dumps(before, ensure_ascii=False))
        if before["frame"] != [0, 0]:
            failures.append(f"before: unexpected frame {before['frame']}")

        # ---- apply the candidate fix ----
        add_minimize_box(hwnd)
        time.sleep(1.5)

        after = snapshot(hwnd)
        report["after"] = after
        print("\nAFTER  " + json.dumps(after, ensure_ascii=False))

        # requirement 1: still no native frame, still no caption
        if after["frame"] != [0, 0]:
            failures.append(f"after: native frame appeared {after['frame']}")
        if after["has_caption"]:
            failures.append("after: WS_CAPTION came back")
        # requirement 6: size must not drift
        if after["client"] != [WINDOW_WIDTH, WINDOW_HEIGHT]:
            failures.append(f"after: client changed {after['client']}")
        # the point of the change
        if not after["WS_MINIMIZEBOX"]:
            failures.append("after: WS_MINIMIZEBOX did not stick")
        items = (after.get("system_menu") or {}).get("items") or {}
        if items.get("Minimize") != "enabled":
            failures.append(f"after: system menu Minimize is {items.get('Minimize')!r}, expected 'enabled'")

        # ---- the message path must still work ----
        print("\n-- SC_MINIMIZE / SC_RESTORE after the change --")
        user32.SendMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_MINIMIZE, 0)
        time.sleep(1.2)
        iconic = W.is_iconic(hwnd)
        print(f"   SendMessage(SC_MINIMIZE) -> iconic={iconic}")
        if not iconic:
            failures.append("after: SC_MINIMIZE stopped working")
        user32.SendMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_RESTORE, 0)
        time.sleep(1.2)
        restored = not W.is_iconic(hwnd)
        print(f"   SendMessage(SC_RESTORE)  -> restored={restored}")
        if not restored:
            failures.append("after: SC_RESTORE stopped working")

        # ---- does the style survive a minimize/restore cycle? ----
        print("\n-- does the style survive minimize/restore? --")
        W.minimize_window(hwnd)
        time.sleep(1.2)
        W.restore_window(hwnd)
        time.sleep(1.2)
        settled = snapshot(hwnd)
        report["after_cycle"] = settled
        print("SETTLED " + json.dumps({k: v for k, v in settled.items() if k != "system_menu"}, ensure_ascii=False))
        if settled["frame"] != [0, 0]:
            failures.append(f"after cycle: native frame {settled['frame']}")
        if settled["client"] != [WINDOW_WIDTH, WINDOW_HEIGHT]:
            failures.append(f"after cycle: client {settled['client']}")
        if not settled["WS_MINIMIZEBOX"]:
            failures.append("after cycle: WS_MINIMIZEBOX was lost (Tk re-applied the style?)")

        # ---- and does Tk overwrite it on its own? watch for a few seconds ----
        print("\n-- watching 6 s to see whether Tk re-applies the style --")
        for _ in range(6):
            time.sleep(1.0)
            now = W.get_style(hwnd)
            if not (now & W.WS_MINIMIZEBOX):
                failures.append("style: WS_MINIMIZEBOX disappeared while idle")
                print("   LOST")
                break
        else:
            print("   still present")

        # ---- the system menu also offers Maximize; can that corrupt the geometry?
        # Requirement 6 says the window must stay 820x500, so a Maximize that does
        # not fully recover would be worse than the bug we are fixing.
        print("\n-- SC_MAXIMIZE then SC_RESTORE (does the fixed size survive?) --")
        user32.SendMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_MAXIMIZE, 0)
        time.sleep(1.5)
        maximized = snapshot(hwnd)
        report["after_maximize"] = maximized
        print(
            "   MAXIMIZED "
            + json.dumps({k: v for k, v in maximized.items() if k != "system_menu"}, ensure_ascii=False)
        )
        user32.SendMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_RESTORE, 0)
        time.sleep(1.5)
        recovered = snapshot(hwnd)
        report["after_maximize_restore"] = recovered
        print(
            "   RESTORED  "
            + json.dumps({k: v for k, v in recovered.items() if k != "system_menu"}, ensure_ascii=False)
        )
        if recovered["client"] != [WINDOW_WIDTH, WINDOW_HEIGHT]:
            failures.append(f"maximize: client did not recover {recovered['client']}")
        if recovered["frame"] != [0, 0]:
            failures.append(f"maximize: frame did not recover {recovered['frame']}")

        report["alive"] = process_alive(pid)
        report["failures"] = failures
        verdict = "PASS" if not failures else "FAIL"
        print("\nSUMMARY " + json.dumps({"verdict": verdict, "failures": failures}, ensure_ascii=False))
        return 0 if not failures else 1
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
