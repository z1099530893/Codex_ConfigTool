"""Serve the *packaged* Qt window for the restore-flash harness.

``proto_restore_flash.py --framework qt-exe`` launches this, so the measurement
runs against ``dist/CodexConfigTool-Qt.exe`` - the artifact that actually ships -
rather than against the source.

That distinction is not academic.  The source build's top-level window has **zero**
native child windows, which is the whole reason the Qt port does not flicker; the
packaged build's window was measured with **two** (a 38px title strip and the
462px content area, both ``Qt6112QWindowIcon``).  Same code, different artifact.
Every previous flash measurement was taken on the source build, so the shipping
build's restore behaviour had never been measured at all.

The app reads its settings from ``%APPDATA%/CodexConfigTool``, so this points
APPDATA at a scratch directory and pre-seeds ``hide_onboarding`` - a modal dialog
at startup would both perturb the timing and be a window the harness has to
dismiss before it can measure anything.

Prints ``SERVE_HWND=<hex>`` on stdout, then waits to be terminated.

    "C:/Program Files/Develop/Python/python.exe" prototypes/serve_qt_exe.py
"""

from __future__ import annotations

import ctypes
import json
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

EXE = ROOT / "dist" / "CodexConfigTool-Qt.exe"
ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def visible_windows() -> list[int]:
    found: list[int] = []

    def callback(hwnd, _lparam):
        if winapi.user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
        return True

    winapi.user32.EnumWindows(ENUM_PROC(callback), 0)
    return found


def main() -> int:
    if not EXE.exists():
        print(f"MISSING EXE {EXE}", file=sys.stderr)
        return 2

    sandbox = Path(tempfile.mkdtemp(prefix="codex-flash-"))
    settings_dir = sandbox / "CodexConfigTool"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"hide_onboarding": True}), encoding="utf-8"
    )

    environment = dict(os.environ)
    environment["APPDATA"] = str(sandbox)
    before = set(visible_windows())
    process = subprocess.Popen(
        [str(EXE)], env=environment, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    hwnd = 0
    deadline = time.time() + 40
    try:
        while time.time() < deadline and not hwnd:
            for candidate in visible_windows():
                if candidate in before:
                    continue
                if not winapi.class_name(candidate).startswith("Qt"):
                    continue
                _left, _top, width, height = winapi.window_rect(candidate)
                if width >= 700 and height >= 400:
                    hwnd = candidate
                    break
            time.sleep(0.3)

        if not hwnd:
            print("no window appeared", file=sys.stderr)
            return 1

        # Anything else the app opened - a dialog, a toast - would sit over the
        # strip being measured.  The settings above should mean there is nothing,
        # but check rather than assume.
        time.sleep(1.0)
        extras = [h for h in visible_windows() if h not in before and h != hwnd]
        for extra in extras:
            winapi.user32.PostMessageW(wintypes.HWND(extra), 0x0010, 0, 0)  # WM_CLOSE
        if extras:
            time.sleep(0.5)

        print(f"SERVE_HWND={hwnd:#x}", flush=True)
        while True:
            time.sleep(0.5)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(sandbox, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
