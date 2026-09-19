"""Count native child windows for the source build and the packaged build.

The Qt port's whole reason for existing is that its top-level window has **no
native child windows** - that is what removes the blank frame on restore.  The
flash probe reports ``native_descendants=0`` for the source build, so a packaged
launch check that reports 2 is either finding a different window or measuring a
different build.

This prints every visible top-level window the app owns, with its class, rect,
style and child count, so the difference is a fact rather than a guess.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_native_children.py
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import winapi  # noqa: E402

ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def visible_windows() -> list[int]:
    found: list[int] = []

    def callback(hwnd, _lparam):
        if winapi.user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
        return True

    winapi.user32.EnumWindows(ENUM_PROC(callback), 0)
    return found


def report(label: str, new_windows: list[int]) -> None:
    print(f"\n=== {label} ===")
    for hwnd in new_windows:
        cls = winapi.class_name(hwnd)
        left, top, width, height = winapi.window_rect(hwnd)
        children = winapi.child_windows(hwnd)
        print(
            f"  {hwnd:#010x} {cls:<24} rect=({left},{top},{width},{height}) "
            f"style={winapi.get_style(hwnd):#010x} children={len(children)}"
        )
        for child in children:
            cleft, ctop, cwidth, cheight = winapi.window_rect(child)
            print(
                f"      child {winapi.class_name(child):<22} "
                f"rect=({cleft},{ctop},{cwidth},{cheight}) style={winapi.get_style(child):#010x}"
            )


def run(label: str, command: list[str], environment: dict) -> None:
    before = set(visible_windows())
    process = subprocess.Popen(
        command, env=environment, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        time.sleep(12)  # long enough for the onboarding dialog to appear too
        new = [h for h in visible_windows() if h not in before]
        report(label, new)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    sandbox = tempfile.mkdtemp(prefix="codex-children-")
    environment = dict(os.environ)
    environment["APPDATA"] = sandbox
    try:
        run(
            "packaged: dist/CodexConfigTool-Qt.exe",
            [str(ROOT / "dist" / "CodexConfigTool-Qt.exe")],
            environment,
        )
        run(
            "source: serve_qt_app.py",
            [sys.executable, str(HERE / "serve_qt_app.py")],
            environment,
        )
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
