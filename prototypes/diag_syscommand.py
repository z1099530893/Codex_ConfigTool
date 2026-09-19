"""Why does clicking the taskbar button not toggle minimize/restore?

Synthetic input is not needed for this one.  Clicking a taskbar button ultimately
asks the window to minimize through ``WM_SYSCOMMAND``/``SC_MINIMIZE``, and the
taskbar jump list's Minimize/Maximize entries are just the window's *system menu*
items.  Both can be inspected directly:

* ``GetSystemMenu`` + ``GetMenuState`` - does the window even have a Minimize
  item, and is it enabled?  A greyed item is what makes Explorer treat the
  taskbar button as activate-only.
* ``SendMessage(WM_SYSCOMMAND, SC_MINIMIZE)`` - does the message path that
  Explorer uses actually minimize the window, compared with a direct
  ``ShowWindow(SW_MINIMIZE)``?

Usage:
    python diag_syscommand.py
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

user32 = ctypes.windll.user32

WM_SYSCOMMAND = 0x0112
SC_MINIMIZE = W.SC_MINIMIZE
SC_RESTORE = W.SC_RESTORE

user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = ctypes.c_void_p


def system_menu_report(hwnd) -> dict:
    """Kept as a thin alias so the prototype reads the same as before."""
    return W.system_menu_report(hwnd)


def styles(hwnd) -> dict:
    style = W.get_style(hwnd)
    return {
        "style": hex(style),
        "WS_POPUP": bool(style & W.WS_POPUP),
        "WS_CAPTION": bool(style & W.WS_CAPTION),
        "WS_SYSMENU": bool(style & W.WS_SYSMENU),
        "WS_MINIMIZEBOX": bool(style & W.WS_MINIMIZEBOX),
        "WS_MAXIMIZEBOX": bool(style & W.WS_MAXIMIZEBOX),
        "WS_THICKFRAME": bool(style & W.WS_THICKFRAME),
        "WS_BORDER": bool(style & W.WS_BORDER),
        "frame_thickness": list(W.frame_thickness(hwnd)),
        "client": list(W.client_rect(hwnd)),
    }


def main() -> int:
    pre = set(all_visible_windows())
    process = subprocess.Popen([os.path.join(ROOT, "dist", "CodexConfigTool.exe")], cwd=ROOT)
    hwnd, pid = find_main_window(pre)
    if not hwnd:
        print("main window not found")
        return 2
    time.sleep(2.5)

    report: dict = {"hwnd": hex(hwnd), "pid": pid}
    print(f"window {hwnd:#x} pid={pid} {W.describe(hwnd)}")

    try:
        report["styles"] = styles(hwnd)
        report["system_menu"] = system_menu_report(hwnd)
        print("styles      " + json.dumps(report["styles"], ensure_ascii=False))
        print("system menu " + json.dumps(report["system_menu"], ensure_ascii=False))

        # --- 1. the message path Explorer uses when you click the taskbar button
        print("\n-- WM_SYSCOMMAND / SC_MINIMIZE (what a taskbar click sends) --")
        user32.SendMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_MINIMIZE, 0)
        time.sleep(1.2)
        via_syscommand = W.is_iconic(hwnd)
        print(f"   after SendMessage(SC_MINIMIZE): iconic={via_syscommand}")
        report["syscommand_sc_minimize_works"] = via_syscommand

        if via_syscommand:
            user32.SendMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_RESTORE, 0)
            time.sleep(1.2)
            print(f"   after SendMessage(SC_RESTORE):  iconic={W.is_iconic(hwnd)}")
            report["syscommand_sc_restore_works"] = not W.is_iconic(hwnd)

        # --- 2. the direct Win32 path, which is known to work
        print("\n-- ShowWindow(SW_MINIMIZE) (the path the custom button uses) --")
        if W.is_iconic(hwnd):
            W.restore_window(hwnd)
            time.sleep(1.0)
        W.minimize_window(hwnd)
        time.sleep(1.2)
        direct = W.is_iconic(hwnd)
        print(f"   after ShowWindow(SW_MINIMIZE): iconic={direct}")
        report["showwindow_minimize_works"] = direct
        W.restore_window(hwnd)
        time.sleep(1.0)

        # --- 3. PostMessage variant (Explorer sometimes posts rather than sends)
        print("\n-- PostMessage(WM_SYSCOMMAND, SC_MINIMIZE) --")
        user32.PostMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_MINIMIZE, 0)
        time.sleep(1.5)
        posted = W.is_iconic(hwnd)
        print(f"   after PostMessage(SC_MINIMIZE): iconic={posted}")
        report["postmessage_sc_minimize_works"] = posted
        if posted:
            W.restore_window(hwnd)
            time.sleep(1.0)

        report["alive"] = process_alive(pid)
        report["final"] = styles(hwnd)

        verdict = (
            "PASS"
            if report.get("syscommand_sc_minimize_works")
            else "REPRODUCED: WM_SYSCOMMAND/SC_MINIMIZE does not minimize"
        )
        print("\nSUMMARY " + json.dumps({"verdict": verdict, **report}, ensure_ascii=False))
        return 0 if verdict == "PASS" else 1
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
