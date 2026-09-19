"""Does ``WS_EX_COMPOSITED``'s idle repaint loop scale with the child count?

Why this exists
---------------
`diag_idle_paint.py` showed that `WS_EX_COMPOSITED` costs ~26% of a core while the
window is simply open, and that the cost is a **repaint loop**: ~55 visible child
windows each receive `WM_NCPAINT` + `WM_ERASEBKGND` + `WM_PAINT` about 22 times a
second, while the unmodified window receives nothing at all.  The loop stops dead
when the window is minimized.

That raises the question this prototype answers, and it is the question that decides
between the two remaining options:

* if the loop's cost scales with the number of child HWNDs, then collapsing 118
  children into one surface would make `WS_EX_COMPOSITED` **cheap as well as
  effective** - the structural rewrite would fix the flash *and* remove the reason
  the fix was rejected; or
* if the cost is flat, the loop is a fixed tax on any composited window and the
  rewrite does nothing for it.

It builds the smallest possible stand-in: an `overrideredirect` Tk window of the
same size, with a controllable number of real Tk children (each Tk widget is a real
HWND), and measures **its own** process CPU with and without `WS_EX_COMPOSITED`.

Two-mode design, and it is not a style choice
---------------------------------------------
Applying `WS_EX_COMPOSITED` to a window owned by the **foreground** process kills the
caller outright (the whole shell invocation is terminated, with no output at all).
Measured here, twice, with a minimal probe.  The same style on a window owned by a
**subprocess** is fine, and every earlier measurement in this investigation used a
subprocess for exactly that reason.  So this file runs the window in `--child` mode
and a parent driver spawns it.

Usage:
    python proto_composited_children.py --children 118 --composited
    python proto_composited_children.py --sweep
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
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

WS_EX_COMPOSITED = 0x02000000
WS_EX_APPWINDOW = 0x00040000
SWP_FRAME_ONLY = 0x0027
GWL_EXSTYLE = -20
GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
FILETIME_TICKS_PER_SECOND = 10_000_000

WIDTH, HEIGHT = 820, 500


def process_cpu_seconds(pid: int) -> float | None:
    """Own user+kernel CPU seconds, so the child needs no parent-side sampler.

    ``OpenProcess`` returns a **handle**, and without an explicit ``restype`` ctypes
    assumes ``c_int`` and truncates it to 32 bits.  ``GetProcessTimes`` then fails on
    the truncated value and ``CloseHandle`` on it takes the process down - which is how
    an earlier version of this file died with no output at all.
    """
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created, exited = wintypes.FILETIME(), wintypes.FILETIME()
        kernel, user = wintypes.FILETIME(), wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None

        def ticks(value):
            return (value.dwHighDateTime << 32) | value.dwLowDateTime

        return round((ticks(kernel) + ticks(user)) / FILETIME_TICKS_PER_SECOND, 4)
    finally:
        kernel32.CloseHandle(handle)


def child_main(args) -> int:
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{WIDTH}x{HEIGHT}+120+120")
    root.configure(bg="#f3f4f7")

    # A mix of the classes the real tree is made of (TkChild / Static / Button),
    # because a class-specific trigger would otherwise be missed.
    widget_width, widget_height = args.size
    per_row = max(1, WIDTH // max(1, widget_width))
    for index in range(args.children):
        row, column = divmod(index, per_row)
        if index % 5 == 0:
            widget = tk.Button(root, text=f"b{index}", bg="#e8eaee", relief="flat")
        else:
            widget = tk.Label(root, text=f"l{index}", bg="#eef0f4", fg="#333333")
        widget.place(
            x=(column * widget_width) % max(1, WIDTH - widget_width),
            y=(row * widget_height) % max(1, HEIGHT - widget_height),
            width=widget_width,
            height=widget_height,
        )
    root.update()
    root.update_idletasks()

    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
    user32.SetWindowLongW.restype = ctypes.c_long

    hwnd = user32.GetAncestor(root.winfo_id(), GA_ROOT)
    user32.SetWindowLongW(
        hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_APPWINDOW
    )
    if args.composited:
        user32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_COMPOSITED,
        )
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAME_ONLY)

    final = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    pid = os.getpid()

    # ``root.update()`` *blocks* once the window is composited - measured: the child
    # hung there and never reached its first log line.  So drive the loop with
    # ``after`` + ``mainloop`` instead, which is what the real application does.
    progress = open(
        os.path.join(HERE, "out", "proto-composited-child.log"), "a", encoding="utf-8"
    )
    progress.write(
        f"--- children={args.children} composited={args.composited} "
        f"exstyle={final:#010x} ---\n"
    )
    progress.flush()
    state = {"window": 0, "before": None, "started": 0.0, "samples": []}

    def finish() -> None:
        progress.write("sampled\n")
        progress.close()
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "children": args.children,
                    "composited": args.composited,
                    "exstyle": final,
                    "seconds": args.seconds,
                    "samples": state["samples"],
                },
                handle,
            )
        root.quit()

    def end_sample() -> None:
        after = process_cpu_seconds(pid)
        before = state["before"]
        wall = time.time() - state["started"]
        sample = None if before is None or after is None else round(after - before, 4)
        state["samples"].append(sample)
        progress.write(f"window {state['window'] + 1}: {sample}s over {wall:.1f}s\n")
        progress.flush()
        state["window"] += 1
        sample_next()

    def sample_next() -> None:
        if state["window"] >= args.windows:
            finish()
            return
        state["before"] = process_cpu_seconds(pid)
        state["started"] = time.time()
        root.after(int(args.seconds * 1000), end_sample)

    def begin() -> None:
        progress.write("settled\n")
        progress.flush()
        sample_next()

    root.after(int(args.settle * 1000), begin)
    root.mainloop()
    return 0


def run_one(
    children: int, composited: bool, seconds: float, windows: int, settle: float, size: str
):
    report = os.path.join(HERE, "out", "proto-composited-child.json")
    command = [
        sys.executable,
        os.path.abspath(__file__),
        "--child",
        "--children",
        str(children),
        "--seconds",
        str(seconds),
        "--windows",
        str(windows),
        "--settle",
        str(settle),
        "--size",
        size,
        "--report",
        report,
    ]
    if composited:
        command.append("--composited")
    if os.path.exists(report):
        os.remove(report)
    # The timeout is not decoration.  With ``WS_EX_COMPOSITED`` the child's Tk event
    # loop can stop going idle, so ``root.update()`` never returns and the child hangs
    # forever.  Without this the parent blocks on it, the whole invocation is killed
    # from outside, and the run produces no output at all - which reads as "the
    # prototype is broken" rather than "the composited window never idles".
    budget = settle + windows * seconds + 30.0
    try:
        subprocess.run(command, cwd=ROOT, capture_output=True, check=False, timeout=budget)
    except subprocess.TimeoutExpired:
        return {"timeout": True, "budget": budget}
    if not os.path.exists(report):
        return None
    with open(report, encoding="utf-8") as handle:
        return json.load(handle)


def describe(result) -> str:
    if result is None:
        return "child produced no report (it died)"
    if result.get("timeout"):
        return (
            f"child HUNG and was killed after {result['budget']:.0f}s - its Tk event "
            f"loop never went idle (see out/proto-composited-child.log)"
        )
    valid = [s for s in result["samples"] if s is not None]
    mean = round(sum(valid) / len(valid), 4) if valid else None
    return (
        f"exstyle={result['exstyle']:#010x} mean={mean}s/{result['seconds']:.0f}s "
        f"samples={result['samples']}"
    )


def parse_size(text: str) -> tuple[int, int]:
    width, _, height = text.partition("x")
    return int(width), int(height)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--children", type=int, default=118)
    parser.add_argument("--composited", action="store_true")
    parser.add_argument("--size", default="60x30", help="WxH of each widget")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--settle", type=float, default=3.0)
    parser.add_argument("--sweep", action="store_true", help="vary the child count")
    parser.add_argument(
        "--area-sweep",
        action="store_true",
        help="fix the child count and vary each widget's area - this separates a "
        "per-child tax from a per-painted-pixel tax",
    )
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--report", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.child:
        args.size = parse_size(args.size)
        return child_main(args)

    if not args.sweep and not args.area_sweep:
        result = run_one(
            args.children,
            args.composited,
            args.seconds,
            args.windows,
            args.settle,
            args.size,
        )
        print(
            f"children={args.children:<4} size={args.size:<8} "
            f"composited={str(args.composited):<5} {describe(result)}"
        )
        return 0

    if args.area_sweep:
        print("fixed 56 children, varying each widget's area (composited only)")
        print(f"{'size':>10}  {'area each':>10}  {'total area':>11}  detail")
        for size in ("30x15", "60x30", "120x60", "240x120"):
            width, height = parse_size(size)
            result = run_one(56, True, args.seconds, args.windows, args.settle, size)
            print(
                f"{size:>10}  {width * height:>10}  {width * height * 56:>11}  "
                f"{describe(result)}"
            )
        return 0

    print(f"{'children':>8}  {'composited':>10}  detail")
    for count in (2, 8, 24, 56, 118):
        for composited in (False, True):
            result = run_one(
                count, composited, args.seconds, args.windows, args.settle, args.size
            )
            print(f"{count:>8}  {str(composited):>10}  {describe(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
