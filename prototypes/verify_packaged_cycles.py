"""The packaged acceptance run's minimise/restore cycles, with no synthetic input.

``accept_packaged_exe.py`` is the real acceptance harness, and it refuses to run
when the desktop will not accept synthetic input - correctly, because otherwise
every click lands at the real cursor position and the app gets blamed for it.
But that pre-flight comes first, so a session that cannot inject input blocks the
*entire* packaged verification, and the cycles below are the regression-prone
part of it: they are what the whole window-chrome effort exists to protect.

So this script drives the same cycles through the Win32 API instead of the mouse.
It is deliberately **not** a substitute for the acceptance run, and the coverage
difference is the whole point:

    covered without input
      1. exactly one custom title bar on open   (frame 0, no WS_CAPTION, no native children)
      3. minimise works and the process survives  (but NOT via the app's own button)
      5. restoring yields one title bar only
      6. repeated minimise/restore never changes the 820x500 size

    NOT covered - needs synthetic input or a screen capture, and only
    accept_packaged_exe.py can do it
      2. dragging the custom title bar
      3. the *click* path: that clicking the app's own minimise button does the above
      4. that a taskbar button really appears - see below
      5. the *click* path: that clicking the real taskbar button restores the window

Requirement 7 (configuration behaviour) is the unit suite's job, not this one's.

Why requirement 4 is not checkable here: the obvious ground truth,
``winapi.taskbar_has_window_title``, walks ``MSTaskListWClass`` button children
and reads their text.  Measured on this Windows 11 desktop, that class exists but
has no text-bearing button children at all, so the helper returns 0 labels for a
window that plainly has a button - it was written for the Windows 7-10 shell and
had never been called.  The capture-based detector the acceptance harness uses
does work, but it needs the window to own the foreground for the active highlight
to appear, and a detector that reports "no button" for a merely unfocused window
is the exact false failure the README documents for the soak test.  Rather than
add a third unreliable check, requirement 4 is left to the acceptance run.

Two geometry traps are avoided below, both of which produced false failures when
this script was first written:

* **Geometry while minimised is meaningless.**  An iconic window reports its
  parked rect, not its real one - the archived passing acceptance report records
  ``client [0, 0], frame [160, 28]`` in that state for a 820x500 window.  Only
  the iconic flag and process liveness are asserted while minimised; the size is
  asserted after restore, where it means something.
* **A style-based proxy is not a presence check.**  ``WS_SYSMENU |
  WS_MINIMIZEBOX`` says the Shell *would* give the window a button, which the
  launch check already covers; it does not say a button is there.

    "C:/Program Files/Develop/Python/python.exe" prototypes/verify_packaged_cycles.py

Needs an interpreter with PIL?  No - nothing here imports ``grab``.  But run it
with the system interpreter anyway if you are running both, so the two report the
same thing.  Exit code 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import winapi as W  # noqa: E402
import verify_packaged_launch as launch  # noqa: E402

EXE = launch.EXE
WINDOW_CLASS_PREFIX = launch.WINDOW_CLASS_PREFIX
EXPECTED_CLIENT = launch.EXPECTED_CLIENT
CYCLES = 5
SETTLE = 1.2


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    W.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def pid_alive(pid: int) -> bool:
    """True while the process is still there.

    ``process_cpu_seconds`` returns ``None`` when the process cannot be opened,
    which covers both "it exited" and "it is gone"; for a liveness assertion that
    distinction does not matter.
    """
    return W.process_cpu_seconds(pid) is not None


def main() -> int:
    if not EXE.exists():
        print(f"MISSING EXE {EXE}")
        return 2

    real_before = launch.settings_digest()
    pre_existing = set(launch.visible_windows())
    sandbox, environment = launch.make_sandbox()

    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, ok, detail))

    process = subprocess.Popen([str(EXE)], env=environment, cwd=str(ROOT))
    try:
        hwnd = launch.find_window(pre_existing)
        if not hwnd:
            print("FAIL the packaged window never appeared")
            print("     (a running instance holds the single-instance mutex; close it and retry)")
            return 1
        time.sleep(1.5)  # let it settle and paint

        title = W.window_text(hwnd)
        pid = window_pid(hwnd)
        print(f"window {W.class_name(hwnd)} title={title!r} pid={pid}")

        # --- the open state (requirement 1) --------------------------------- #
        check("open: no native frame", W.frame_thickness(hwnd) == (0, 0),
              str(W.frame_thickness(hwnd)))
        check("open: no WS_CAPTION", not (W.get_style(hwnd) & W.WS_CAPTION),
              hex(W.get_style(hwnd)))
        check("open: no native children", not W._descendants(hwnd),
              f"{len(W._descendants(hwnd))} found")
        check("open: client is 820x500", W.client_rect(hwnd) == EXPECTED_CLIENT,
              str(W.client_rect(hwnd)))

        for index in range(1, CYCLES + 1):
            tag = f"cycle{index}"

            # Recover from a previous cycle that failed to restore, so one bad
            # cycle does not cascade into every later one looking wrong.
            if W.is_iconic(hwnd):
                W.restore_window(hwnd)
                time.sleep(SETTLE)

            check(f"{tag}: normal, not minimised", not W.is_iconic(hwnd),
                  f"iconic={W.is_iconic(hwnd)}")

            # --- minimise (requirement 3, API path only) -------------------- #
            # Only the iconic flag and liveness are asserted here: an iconic
            # window reports its parked rect, so any geometry read in this state
            # is meaningless and asserting on it invents failures.
            W.minimize_window(hwnd)
            time.sleep(SETTLE)
            check(f"{tag}: minimised", W.is_iconic(hwnd), f"iconic={W.is_iconic(hwnd)}")
            check(f"{tag}: process alive after minimise", pid_alive(pid), f"pid {pid}")
            check(f"{tag}: still visible while minimised", W.is_visible(hwnd),
                  f"visible={W.is_visible(hwnd)}")

            # --- restore (requirement 5/6, API path only) ------------------- #
            W.restore_window(hwnd)
            time.sleep(SETTLE)
            check(f"{tag}: restored", not W.is_iconic(hwnd), f"iconic={W.is_iconic(hwnd)}")
            check(f"{tag}: client is 820x500 after restore",
                  W.client_rect(hwnd) == EXPECTED_CLIENT, str(W.client_rect(hwnd)))
            check(f"{tag}: no native frame after restore",
                  W.frame_thickness(hwnd) == (0, 0), str(W.frame_thickness(hwnd)))
            check(f"{tag}: no WS_CAPTION after restore",
                  not (W.get_style(hwnd) & W.WS_CAPTION), hex(W.get_style(hwnd)))
            check(f"{tag}: no native children after restore",
                  not W._descendants(hwnd), f"{len(W._descendants(hwnd))} found")
            check(f"{tag}: process alive after restore", pid_alive(pid), f"pid {pid}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(sandbox, ignore_errors=True)

    real_after = launch.settings_digest()
    check("real settings.json untouched", real_before == real_after, real_before[:16])

    for label, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}  -- {detail}")

    failed = [label for label, ok, _ in checks if not ok]
    print()
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed over {CYCLES} cycles")
    print("PACKAGED CYCLES OK" if not failed else f"FAILED: {', '.join(failed)}")
    print()
    print("note: the cycles above were driven through the Win32 API, NOT by clicking.")
    print("      NOT covered: the title-bar drag; the click paths of the app's own")
    print("      minimise button and of the real taskbar button; and that a taskbar")
    print("      button actually appears (not readable from the Shell task list on")
    print("      Windows 11). Only accept_packaged_exe.py covers those, and it needs")
    print("      synthetic input.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
