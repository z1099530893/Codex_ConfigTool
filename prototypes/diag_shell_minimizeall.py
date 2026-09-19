"""Prove the Shell now treats the window as minimizable - without synthetic input.

Synthetic input is often unavailable on a shared desktop, which blocks the one
test that matters most: "click the taskbar icon and see if it toggles".  There is
a way around it.

``Shell.MinimizeAll()`` (the "show desktop" / Win+D command) minimizes every
window the Shell considers minimizable, and the Shell decides that from
``WS_MINIMIZEBOX`` - the same rule that makes the taskbar button toggle instead
of merely activating.  So if the window gets minimized by ``MinimizeAll`` but did
not before the fix, the Shell's decision has changed, which is exactly the thing
the taskbar click depends on.

Minimizing every window is visible, so this is deliberately reversible: the set
of windows that were *not* minimized before the command are recorded, and any of
them that MinimizeAll minimized are restored afterwards (maximized ones with
``SW_SHOWMAXIMIZED``, so a maximized window does not come back un-maximized).

Usage:
    python diag_shell_minimizeall.py
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

import winapi as W  # noqa: E402
from accept_packaged_exe import all_visible_windows, find_main_window, process_alive  # noqa: E402

SHELL_MINIMIZE_ALL = "(New-Object -ComObject Shell.Application).MinimizeAll()"
SHELL_UNDO = "(New-Object -ComObject Shell.Application).UndoMinimizeALL()"

SW_SHOWMAXIMIZED = 3
SW_SHOWNORMAL = 1


def shell(command: str) -> bool:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"   powershell failed: {(result.stderr or result.stdout).strip()[:200]}")
    return result.returncode == 0


def snapshot(hwnds) -> dict:
    state = {}
    for hwnd in hwnds:
        if not W.user32.IsWindow(hwnd):
            continue
        state[hwnd] = {
            "iconic": W.is_iconic(hwnd),
            "zoomed": bool(W.user32.IsZoomed(hwnd)),
            "class": W.class_name(hwnd),
            "title": W.window_text(hwnd)[:40],
        }
    return state


def restore(before: dict, after: dict) -> list[str]:
    """Undo only what this test changed: non-iconic -> iconic."""
    changed = []
    for hwnd, prior in before.items():
        if prior["iconic"]:
            continue  # it was already minimized; leave it alone
        now = after.get(hwnd)
        if not now or not now["iconic"]:
            continue
        W.user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED if prior["zoomed"] else SW_SHOWNORMAL)
        changed.append(f"{prior['class']}:{prior['title']}")
    return changed


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--exe",
        default=os.path.join(ROOT, "dist", "CodexConfigTool.exe"),
        help="which build to test; point it at the pre-fix backup for a control run",
    )
    args = parser.parse_args()

    pre = set(all_visible_windows())
    process = subprocess.Popen([args.exe], cwd=ROOT)
    hwnd, pid = find_main_window(pre)
    if not hwnd:
        print("main window not found")
        return 2
    time.sleep(2.5)

    style = W.get_style(hwnd)
    print(f"exe    {args.exe}")
    print(f"window {hwnd:#x} style={hex(style)}")
    print("WS_MINIMIZEBOX =", bool(style & W.WS_MINIMIZEBOX))
    print("system menu    =", json.dumps(W.system_menu_report(hwnd), ensure_ascii=False))

    try:
        # windows that are currently *not* minimized, so we know what to put back
        before = snapshot(all_visible_windows())
        print(f"\ntracking {len(before)} visible windows")

        print("\n-- Shell.MinimizeAll() --")
        ok = shell(SHELL_MINIMIZE_ALL)
        time.sleep(2.5)
        after = snapshot(before.keys())

        app_minimized = W.is_iconic(hwnd)
        print(f"   our window iconic after MinimizeAll: {app_minimized}")
        others = [h for h, s in after.items() if s["iconic"] and not before.get(h, {}).get("iconic")]

        print("\n-- restoring everything this test minimized --")
        shell(SHELL_UNDO)
        time.sleep(1.0)
        # belt and braces: UndoMinimizeALL is best-effort, so restore explicitly
        # anything that was visible before and is minimized now.
        now = snapshot(before.keys())
        changed = restore(before, now)
        print(f"   explicitly restored {len(changed)} window(s)")
        for item in changed[:8]:
            print(f"     {item}")
        time.sleep(1.0)
        final = snapshot(before.keys())
        left_minimized = [
            f"{before[h]['class']}:{before[h]['title']}"
            for h, s in final.items()
            if s["iconic"] and not before.get(h, {}).get("iconic")
        ]
        if left_minimized:
            print(f"   WARNING still minimized: {left_minimized[:5]}")

        W.restore_window(hwnd)
        time.sleep(1.0)

        report = {
            "style": hex(style),
            "WS_MINIMIZEBOX": bool(style & W.WS_MINIMIZEBOX),
            "shell_minimize_all_ran": ok,
            "app_minimized_by_shell": app_minimized,
            "other_windows_minimized": len(others),
            "restored": changed,
            "left_minimized": left_minimized,
            "alive": process_alive(pid),
        }
        verdict = (
            "PASS: the Shell now considers the window minimizable"
            if app_minimized
            else "FAIL: the Shell still refuses to minimize the window"
        )
        print("\nSUMMARY " + json.dumps({"verdict": verdict, **report}, ensure_ascii=False))
        return 0 if app_minimized else 1
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
