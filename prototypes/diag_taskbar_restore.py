"""Does clicking our taskbar button actually restore the window?

Minimizes through Win32 (bypassing the custom button entirely), locates the real
taskbar button by diffing the normal and minimized strips, then clicks it while
polling the iconic state.  If the click fails it then tries, in order, what the
shell is believed to send (``WM_SYSCOMMAND``/``SC_RESTORE``) and a plain
``ShowWindow(SW_RESTORE)``, so the failing layer is identifiable.

Usage:
    python diag_taskbar_restore.py [--rounds 3]
"""

from __future__ import annotations

import argparse
import ctypes
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
from accept_packaged_exe import (  # noqa: E402
    TASKBAR_SCAN,
    bbox_of,
    changed_runs,
    describe_runs,
    rightmost_button,
)

EXE = os.path.join(ROOT, "dist", "CodexConfigTool.exe")
OUT = os.path.join(HERE, "out")
WM_SYSCOMMAND = 0x0112
SC_RESTORE = 0xF120

user32 = ctypes.windll.user32
user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = ctypes.c_void_p
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.mouse_event.argtypes = (
    ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p
)


def click(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.15)
    user32.mouse_event(0x0002, 0, 0, 0, None)
    time.sleep(0.10)
    user32.mouse_event(0x0004, 0, 0, 0, None)


def poll(hwnd: int, seconds: float) -> bool:
    """Return True if the window became non-iconic at any point."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not W.is_iconic(hwnd):
            return True
        time.sleep(0.05)
    return not W.is_iconic(hwnd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()

    os.makedirs(OUT, exist_ok=True)
    from accept_packaged_exe import all_visible_windows, find_main_window

    pre = set(all_visible_windows())
    process = subprocess.Popen([EXE], cwd=ROOT)
    hwnd, pid = find_main_window(pre)
    if not hwnd:
        print("main window not found")
        return 2
    time.sleep(2.5)
    print(f"window {hwnd:#x} pid={pid} {W.describe(hwnd)}")
    origin_x, origin_y, _, taskbar_h = grab.taskbar_rect()

    try:
        for round_index in range(1, args.rounds + 1):
            W.restore_window(hwnd)
            time.sleep(0.8)
            normal = os.path.join(OUT, f"tb-{round_index}-normal.png")
            grab.grab_taskbar_strip().save(normal)

            W.minimize_window(hwnd)
            time.sleep(1.2)
            minimized = os.path.join(OUT, f"tb-{round_index}-minimized.png")
            grab.grab_taskbar_strip().save(minimized)

            runs = changed_runs(minimized, normal, TASKBAR_SCAN)
            button = rightmost_button(runs)
            print(f"\n[round {round_index}] iconic after minimize={W.is_iconic(hwnd)}")
            print(f"  runs: {describe_runs(runs)}")
            if not button:
                print("  no button located")
                continue
            bbox = bbox_of(button)
            x = origin_x + (bbox[0] + bbox[2]) // 2
            y = origin_y + (bbox[1] + bbox[3]) // 2
            print(f"  button {bbox} -> click ({x}, {y})")
            print(f"  topmost there: {W.describe_occluder(hwnd, x, y)}")
            click(x, y)
            print(f"  after taskbar click: restored={poll(hwnd, 2.0)} iconic={W.is_iconic(hwnd)}")

            if W.is_iconic(hwnd):
                print("  -> trying WM_SYSCOMMAND/SC_RESTORE (what the shell sends)")
                user32.SendMessageW(wintypes.HWND(hwnd), WM_SYSCOMMAND, SC_RESTORE, 0)
                print(f"     restored={poll(hwnd, 1.5)} iconic={W.is_iconic(hwnd)}")
            if W.is_iconic(hwnd):
                print("  -> trying ShowWindow(SW_RESTORE)")
                W.restore_window(hwnd)
                print(f"     restored={poll(hwnd, 1.5)} iconic={W.is_iconic(hwnd)}")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
