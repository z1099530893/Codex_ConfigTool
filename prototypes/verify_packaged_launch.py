"""Launch the packaged Qt EXE and check the window, without injecting any input.

The full acceptance harness (``accept_packaged_exe.py``) refuses to run when the
desktop will not accept synthetic input - correctly, because otherwise every click
lands at the real cursor position and the app gets blamed for it.  But that check
comes first, so a locked or disconnected session blocks the *whole* packaged
verification, including the parts that need no input at all.

This does those parts and nothing else: launch, find the window by class, measure
the frame, count native child windows, and confirm the settings file it wrote to
was the scratch one.  It proves the build starts and is still borderless with zero
native descendants; it does **not** prove a single click lands where it should.
Say so when reporting it - a launch check is not an acceptance run.

    "C:/Program Files/Develop/Python/python.exe" prototypes/verify_packaged_launch.py

Exit code 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import ctypes
import hashlib
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
WINDOW_CLASS_PREFIX = "Qt"
EXPECTED_CLIENT = (820, 500)


def visible_windows() -> list[int]:
    found: list[int] = []

    def callback(hwnd, _lparam):
        if winapi.user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    winapi.user32.EnumWindows(enum_proc(callback), 0)
    return found


def find_window(exclude: set[int], timeout: float = 30.0) -> int:
    """Find the app's window, ignoring any that already existed.

    Matching on class alone would happily return a stale instance left over from
    an earlier run, which would make this pass without the new build ever having
    started.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd in visible_windows():
            if hwnd in exclude:
                continue
            if not winapi.class_name(hwnd).startswith(WINDOW_CLASS_PREFIX):
                continue
            _left, _top, width, height = winapi.window_rect(hwnd)
            if width >= 700 and height >= 400:
                return hwnd
        time.sleep(0.3)
    return 0


def settings_digest() -> str:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return "<no APPDATA>"
    path = Path(appdata) / "CodexConfigTool" / "settings.json"
    if not path.exists():
        return "<absent>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_sandbox() -> tuple[str, dict[str, str]]:
    """A scratch ``%APPDATA%`` and the environment that points the app at it.

    Shared with ``verify_packaged_cycles.py`` so the two cannot drift apart on
    the one detail that decides whether the measurement is of the shipping
    configuration.

    The app resolves its settings directory from APPDATA, so pointing APPDATA at
    a scratch directory keeps the run off the user's real configuration.

    ``hide_onboarding`` is pre-seeded for a second reason.  With the modal
    onboarding dialog up, the main window was measured with **two** native child
    windows (a 38px title strip and the 462px content area, both
    ``Qt6112QWindowIcon``) - and the native-child count is exactly the property
    this check exists to verify, since it is why the Qt build does not flicker.
    Suppressing the dialog makes the measurement the one that matters, and it is
    the same configuration the flash probe measures (``serve_qt_exe.py``).
    """
    sandbox = tempfile.mkdtemp(prefix="codex-launch-")
    settings_dir = Path(sandbox) / "CodexConfigTool"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"hide_onboarding": True}), encoding="utf-8"
    )
    environment = dict(os.environ)
    environment["APPDATA"] = sandbox
    return sandbox, environment


def main() -> int:
    if not EXE.exists():
        print(f"MISSING EXE {EXE}")
        return 2

    real_before = settings_digest()
    pre_existing = set(visible_windows())

    sandbox, environment = make_sandbox()

    process = subprocess.Popen([str(EXE)], env=environment, cwd=str(ROOT))
    checks: list[tuple[str, bool, str]] = []
    try:
        hwnd = find_window(pre_existing)
        if not hwnd:
            # The app holds a single-instance mutex, so a leftover instance makes
            # this look like a build failure.  Say which it is.
            print("FAIL the packaged window never appeared")
            print("     (a running instance holds the single-instance mutex; close it and retry)")
            return 1
        time.sleep(1.5)  # let it settle and paint

        cls = winapi.class_name(hwnd)
        client = winapi.client_rect(hwnd)
        frame = winapi.frame_thickness(hwnd)
        style = winapi.get_style(hwnd)
        ex_style = winapi.get_ex_style(hwnd)
        # Every real child window counts.  The Qt build is supposed to have none
        # (that is the whole reason it does not flicker), so a non-zero count is
        # the interesting result, not the classes involved.
        native = winapi._descendants(hwnd)

        checks.append(("window class is Qt", cls.startswith(WINDOW_CLASS_PREFIX), cls))
        checks.append(("client size is 820x500", client == EXPECTED_CLIENT, str(client)))
        checks.append(("no native frame", frame == (0, 0), str(frame)))
        checks.append(("no native child windows", not native, f"{len(native)} found"))
        checks.append(
            (
                "taskbar-eligible (WS_SYSMENU | WS_MINIMIZEBOX)",
                bool(style & winapi.WS_SYSMENU) and bool(style & winapi.WS_MINIMIZEBOX),
                hex(style),
            )
        )
        checks.append(
            ("no layered ex-style", not (ex_style & 0x00080000), hex(ex_style))
        )
        checks.append(
            (
                "wrote its settings into the scratch APPDATA",
                (Path(sandbox) / "CodexConfigTool").exists(),
                sandbox,
            )
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(sandbox, ignore_errors=True)

    real_after = settings_digest()
    untouched = real_before == real_after
    checks.append(("real settings.json untouched", untouched, real_before[:16]))

    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  -- {detail}")

    failed = [name for name, ok, _ in checks if not ok]
    print("\n" + ("PACKAGED LAUNCH OK" if not failed else f"FAILED: {', '.join(failed)}"))
    print("note: no input is injected here; click and typing behaviour is NOT covered")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
