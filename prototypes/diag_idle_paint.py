"""Is the app repainting while it just sits there?

Why this exists
---------------
``diag_idle_cpu.py`` measured ``WS_EX_COMPOSITED`` at ~100x the baseline's idle CPU
(2.31 s against 0.02 s over 20 s of doing nothing).  That figure has two very
different explanations, and they call for opposite decisions:

* **intrinsic** - DWM composites a window with 118 child windows from a back
  buffer, and that is simply what it costs; or
* **a repaint loop** - something keeps invalidating the window, and the composited
  path turns every invalidation into a full off-screen redraw of all 118 children.

Only the second is fixable, and if it is the answer then ``WS_EX_COMPOSITED`` is back
on the table as a real option.  Pixels cannot tell the two apart, and neither can a
single CPU number.  This script asks the question two ways at once:

1. **Count the messages that repaint a window**, with nothing of ours touching the
   app's event loop.  A rising ``WM_PAINT`` / ``WM_ERASEBKGND`` / ``WM_TIMER`` count
   is the loop.
2. **Sample the same CPU with the window minimized.**  A minimized window is not
   painted, so a burn that is *presentation*-driven collapses while iconic - and a
   burn that survives minimization is not a repaint at all.

Neither test alone is conclusive.  Together they separate the two explanations.

A note on where the spy lives
-----------------------------
The counting is done by the app itself (``CODEX_VARIANT=... +idlecount``), not by
this script.  That is not a style choice: ``GetWindowLongPtrW(GWLP_WNDPROC)`` returns
0 for a window owned by another process, so a harness-side spy installs **nothing**
and reports an empty message log that looks exactly like a quiet app.  The first
version of this script did that and printed ``spy installed on 0/120`` - the
instrument was broken, not the hypothesis.  The in-process variant writes
``out/idle-messages.log``; this script reads it.

Usage:
    python diag_idle_paint.py --variant composited
    python diag_idle_paint.py                      # baseline, for comparison
    python diag_idle_paint.py --variant composited --seconds 3 --windows 3
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
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

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

        _user32.EnumWindows(
            ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(callback), 0
        )
        return found

    def find_main_window(exclude: set[int], timeout: float = 40.0):
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


IDLE_LOG = os.path.join(HERE, "out", "idle-messages.log")
TRACE_LOG = os.path.join(HERE, "out", "window-trace.log")


def read_log() -> list[str]:
    if not os.path.exists(IDLE_LOG):
        return []
    with open(IDLE_LOG, encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if not line.startswith("#")]


def busy_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if "none" not in line]


def summarize(lines: list[str]) -> str:
    busy = busy_lines(lines)
    if not busy:
        return f"no repaint/move messages in {len(lines)} sampled second(s)"
    return f"{len(busy)}/{len(lines)} sampled second(s) had messages: {busy[:3]}"


def mean(values):
    return round(sum(values) / len(values), 4) if values else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=os.path.join(HERE, "instrumented_app.py"))
    parser.add_argument("--variant", default=None, help="CODEX_VARIANT for the prototype runner")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--settle", type=float, default=6.0)
    args = parser.parse_args()

    features = [part for part in (args.variant or "").split("+") if part]
    if "idlecount" not in features:
        features.append("idlecount")
    variant = "+".join(features)
    label = args.variant or "baseline"

    command = [sys.executable, args.exe]
    environment = dict(os.environ)
    environment["CODEX_VARIANT"] = variant
    environment["CODEX_TRACE"] = "1"
    print(f"=== {label} (variant '{variant}') ===")

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        hwnd, pid = find_main_window(set(all_visible_windows()), timeout=30.0)
        if not hwnd:
            print("main window never appeared")
            return 2
        print(f"window {hwnd:#x} pid={pid} {W.describe(hwnd)}")

        time.sleep(args.settle)

        # The install line is the positive control: without it, a quiet log cannot be
        # told apart from a spy that never attached.
        if os.path.exists(TRACE_LOG):
            with open(TRACE_LOG, encoding="utf-8") as handle:
                for line in handle:
                    if "idlecount:" in line:
                        print(line.strip())

        def sample(phase: str, seconds: float, windows: int) -> list[float]:
            rates = []
            for index in range(windows):
                cpu_before = W.process_cpu_seconds(pid)
                started = time.time()
                time.sleep(seconds)
                wall = time.time() - started
                cpu_after = W.process_cpu_seconds(pid)
                cost = (
                    None
                    if cpu_before is None or cpu_after is None
                    else round(cpu_after - cpu_before, 4)
                )
                if cost is not None:
                    rates.append(cost)
                share = f"{cost / wall * 100:5.2f}%" if cost is not None else "  n/a"
                print(f"{phase:<9} {index + 1}: {cost}s over {wall:.1f}s ({share} of one core)")
            return rates

        print("\n--- phase 1: visible, nothing touching the app ---")
        mark = len(read_log())
        visible = sample("visible", args.seconds, args.windows)
        visible_lines = read_log()[mark:]

        print("\n--- phase 2: minimized (a minimized window is not painted) ---")
        mark = len(read_log())
        if not W.minimize_window(hwnd):
            print("minimize_window failed")
        time.sleep(2.0)
        print(f"  iconic={W.is_iconic(hwnd)}")
        iconic = sample("iconic", args.seconds, args.windows)
        iconic_lines = read_log()[mark:]

        W.restore_window(hwnd)
        time.sleep(1.0)

        print(f"\n=== {label} summary ===")
        print(f"visible  mean cpu per {args.seconds:.0f}s window: {mean(visible)}s  {visible}")
        print(f"iconic   mean cpu per {args.seconds:.0f}s window: {mean(iconic)}s  {iconic}")
        print(f"visible  messages: {summarize(visible_lines)}")
        print(f"iconic   messages: {summarize(iconic_lines)}")
        if mean(visible) and mean(iconic) is not None:
            ratio = mean(iconic) / mean(visible)
            print(f"iconic/visible cpu ratio: {ratio:.2f}")
            print("  ratio near 0  -> the burn is presentation-driven (a repaint path)")
            print("  ratio near 1  -> the burn survives with nothing on screen: not a repaint")
        return 0
    finally:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )


if __name__ == "__main__":
    raise SystemExit(main())
