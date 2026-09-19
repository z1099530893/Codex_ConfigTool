"""Count the window's child HWNDs and attribute them to subtrees.

Why this exists
---------------
The restore flash has resisted eleven candidate fixes (see
``AGENT_HANDOFF_WINDOW_BUGS.md``).  The evidence says the tear is a full repaint
that Tk performs after the re-map storm, in which the parent's background reaches
the screen before the child frames have painted over it - and every child frame is
a separate window that Windows shows and repaints on its own schedule.

That makes the *number of child HWNDs* the thing that decides whether the
remaining structural option is worth taking.  "Replacing the sidebar with a
Canvas" is only a real answer if the sidebar actually owns most of them, so this
measures that instead of guessing.

Usage:
    python diag_child_windows.py                  # packaged build
    python diag_child_windows.py --exe path.exe   # any build
    python diag_child_windows.py --exe app.py     # run from source

Exit codes: 0 ok, 2 harness error, 3 environment.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import winapi as W  # noqa: E402
from accept_packaged_exe import (  # noqa: E402
    all_visible_windows,
    close_existing_app_windows,
    close_existing_instances,
    find_main_window,
)

OUT_DIR = os.path.join(HERE, "out")
APP_TITLE = "Codex 配置助手"


def subtree_size(hwnd: int) -> int:
    """How many windows sit under this one, including itself."""
    return 1 + len(W.child_windows(hwnd))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=os.path.join(ROOT, "dist", "CodexConfigTool.exe"))
    parser.add_argument("--variant", default=os.environ.get("CODEX_VARIANT", ""))
    parser.add_argument("--wait", type=float, default=25.0)
    parser.add_argument(
        "--sidebar-width",
        type=int,
        default=240,
        help="width of the navigation sidebar strip, measured from the left edge",
    )
    args = parser.parse_args()

    exe = os.path.abspath(args.exe)
    if not os.path.exists(exe):
        print(f"HARNESS --exe does not exist: {args.exe} (resolved to {exe})")
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    notes: list[str] = []

    for name in ("CodexConfigTool.exe", os.path.basename(exe)):
        closed = close_existing_instances(name, notes)
        if closed:
            print(f"pre-flight: closed {closed} pre-existing {name} instance(s)")
    closed = close_existing_app_windows(notes)
    if closed:
        print(f"pre-flight: closed {closed} process(es) owning an app window")

    if exe.lower().endswith(".py"):
        command = [sys.executable, exe]
    else:
        command = [exe]

    pre = set(all_visible_windows())
    environment = dict(os.environ)
    if args.variant:
        environment["CODEX_VARIANT"] = args.variant
    process = subprocess.Popen(command, cwd=ROOT, env=environment)

    try:
        hwnd, pid = find_main_window(pre, timeout=args.wait)
        if not hwnd:
            print("main window not found")
            return 2
        time.sleep(1.5)

        style = W.get_style(hwnd)
        print(
            f"window {hwnd:#x} pid={pid} class={W.class_name(hwnd)!r} "
            f"style={style:#010x} rect={W.window_rect(hwnd)}"
        )

        descendants = W.child_windows(hwnd)
        children = W.direct_children(hwnd)
        print(f"\ntotal descendant windows : {len(descendants)}")
        print(f"immediate children       : {len(children)}")
        # Tk nests every widget under a single TkChild that covers the whole
        # window, so "which immediate child owns them" is the wrong question -
        # attribute each window by its own rect instead.
        print(
            "  (Tk puts every widget under one TkChild spanning the client area, "
            "so descendants are attributed by rect, not by parent)"
        )

        by_class: dict[str, int] = {}
        for child in descendants:
            by_class[W.class_name(child)] = by_class.get(W.class_name(child), 0) + 1
        print("\nby window class:")
        for name, count in sorted(by_class.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>5}  {name}")

        root_rect = W.window_rect(hwnd)
        root_left, root_top, root_w, root_h = root_rect
        strip_right = root_left + args.sidebar_width

        rows = []
        for child in descendants:
            rect = W.window_rect(child)
            left, top, width, height = rect
            rows.append(
                {
                    "hwnd": f"{child:#x}",
                    "class": W.class_name(child),
                    "rect": list(rect),
                    "area": width * height,
                    "in_sidebar_strip": width <= root_w and left + width <= strip_right,
                }
            )

        print(f"\nlargest descendants by area (the whole UI, not just the sidebar):")
        print(f"  {'area':>9}  {'class':<10} rect")
        for row in sorted(rows, key=lambda r: -r["area"])[:10]:
            rect = row["rect"]
            print(
                f"  {row['area']:>9}  {row['class']:<10} "
                f"[{rect[0]},{rect[1]},{rect[2]},{rect[3]}]"
            )

        in_strip = [row for row in rows if row["in_sidebar_strip"]]
        strip_classes: dict[str, int] = {}
        for row in in_strip:
            strip_classes[row["class"]] = strip_classes.get(row["class"], 0) + 1

        print(
            f"\ndescendants inside the left {args.sidebar_width}px strip "
            f"(the navigation sidebar): {len(in_strip)} of {len(descendants)} "
            f"({len(in_strip) / max(len(descendants), 1):.0%})"
        )
        print(f"  by class: {strip_classes}")
        print(
            "  -> a single Canvas replacing the sidebar would remove about "
            f"{len(in_strip)} of the {len(descendants)} child windows"
        )

        report = {
            "exe": exe,
            "variant": args.variant or "baseline",
            "hwnd": f"{hwnd:#x}",
            "style": f"{style:#010x}",
            "rect": list(root_rect),
            "descendants": len(descendants),
            "immediate_children": len(children),
            "by_class": by_class,
            "sidebar_width": args.sidebar_width,
            "descendants_in_sidebar_strip": len(in_strip),
            "sidebar_strip_by_class": strip_classes,
            "windows": sorted(rows, key=lambda r: -r["area"]),
        }
        path = os.path.join(OUT_DIR, "child-windows-report.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print("REPORT " + path)
        print("SUMMARY " + json.dumps(
            {
                "descendants": len(descendants),
                "immediate_children": len(children),
                "in_sidebar_strip": len(in_strip),
                "by_class": by_class,
            },
            ensure_ascii=False,
        ))
        return 0
    finally:
        for target in (pid, process.pid):
            if target:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(target)],
                    capture_output=True,
                    check=False,
                )


if __name__ == "__main__":
    raise SystemExit(main())
