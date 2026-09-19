"""Measure the app's CPU cost while it just sits there, with no harness attached.

Why this exists
---------------
``verify_restore_flash.py`` samples idle CPU, but it also captures the screen and
drives the window, so a reviewer is right to ask whether the idle figure is the
app's or the harness's.  This script removes the harness: it launches the app, waits
for it to settle, then measures the app process's own user+kernel CPU over a series
of windows with nothing else running.

The question it answers is the one a frame metric cannot.  ``WS_EX_COMPOSITED``
measurably reduces the restore flash, but it makes DWM composite the window from a
back buffer, and on a window with 118 child windows that can cost real CPU - either
a burst per restore (tolerable) or a steady burn while the window is open (not).
Pixels cannot tell you which; the process's own CPU time can.

Usage:
    python diag_idle_cpu.py                       # the app as it ships
    python diag_idle_cpu.py --variant composited  # with a prototype patch
    python diag_idle_cpu.py --seconds 5 --windows 4
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import ctypes  # noqa: E402
from ctypes import wintypes  # noqa: E402

import winapi as W  # noqa: E402

try:  # the full harness, when this script sits next to it
    from accept_packaged_exe import all_visible_windows, find_main_window
except ImportError:  # standalone (e.g. copied into a skill bundle)
    _user32 = ctypes.windll.user32

    def all_visible_windows() -> list[int]:
        found: list[int] = []

        def callback(hwnd, _lparam):
            if _user32.IsWindowVisible(hwnd):
                found.append(int(hwnd))
            return True

        _user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                               wintypes.LPARAM)(callback), 0)
        return found

    def find_main_window(exclude: set[int], timeout: float = 40.0):
        """Locate the app's main window, ignoring windows that already existed.

        Matches on window class and size, which is why ``exclude`` is required:
        a stale instance from an earlier run would otherwise be picked up.
        Returns ``(hwnd, pid)``.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            for hwnd in all_visible_windows():
                if hwnd in exclude or W.class_name(hwnd) != "TkTopLevel":
                    continue
                _, _, width, height = W.window_rect(hwnd)
                if width >= 700 and height >= 400:
                    owner = wintypes.DWORD()
                    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                    return hwnd, owner.value
            time.sleep(0.4)
        return 0, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=os.path.join(ROOT, "codex_config_tool.py"))
    parser.add_argument("--variant", default=None, help="CODEX_VARIANT for the prototype runner")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--settle", type=float, default=6.0)
    args = parser.parse_args()

    if args.variant and args.exe.endswith(".py") and "instrumented_app" not in args.exe:
        args.exe = os.path.join(HERE, "instrumented_app.py")

    command = [sys.executable, args.exe]
    environment = dict(os.environ)
    if args.variant:
        environment["CODEX_VARIANT"] = args.variant
    print(f"launching {os.path.basename(args.exe)}" + (f" variant={args.variant}" if args.variant else ""))

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # ``exclude`` is required: the search matches on window class and size, so
        # a stale instance from an earlier run would otherwise be picked up.
        hwnd, pid = find_main_window(set(all_visible_windows()), timeout=30.0)
        if not hwnd:
            print("main window never appeared")
            return 2
        print(f"window {hwnd:#x} pid={pid} {W.describe(hwnd)}")

        # Let startup, the <Map> storm and the taskbar registration finish.
        time.sleep(args.settle)

        samples = []
        for window in range(args.windows):
            before = W.process_cpu_seconds(pid)
            started = time.time()
            time.sleep(args.seconds)
            after = W.process_cpu_seconds(pid)
            wall = time.time() - started
            if before is None or after is None:
                print(f"window {window + 1}: cpu unavailable")
                continue
            delta = round(after - before, 4)
            samples.append(delta)
            print(
                f"window {window + 1}: {delta}s cpu over {wall:.1f}s "
                f"({delta / wall * 100:.2f}% of one core)"
            )

        if samples:
            steady = samples[-1]
            print(
                f"\nsteady idle cpu: {steady}s per {args.seconds:.0f}s "
                f"({steady / args.seconds * 100:.2f}% of one core)"
            )
            print(f"all windows: {samples}")
        return 0
    finally:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
