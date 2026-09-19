"""Acceptance test for the PACKAGED executable.

Runs ``dist/CodexConfigTool.exe`` and checks the seven user-confirmed
requirements against the real binary:

  1. exactly one custom (black) title bar on open
  2. dragging the custom title bar does not break the window
  3. the custom minimize button minimizes only; the process stays alive
  4. a taskbar button exists while normal, minimized and restored
  5. restoring shows one title bar only (no native title bar)
  6. repeated minimize/restore never changes the 820x500 size
  7. configuration behaviour is untouched (covered by the unit suite)

Minimize is triggered by clicking the app's real minimize button, and restore by
clicking the real taskbar button, both with synthetic mouse input.

Locating the taskbar button
---------------------------
On this machine the taskbar packs its buttons rightward against the tray, so
adding our button pushes every other button to the left.  A strip captured
before the app launched therefore differs across its *whole* width, and picking
the widest changed run lands on somebody else's button.  Two rules fix that:

* diff two strips captured moments apart with the app already running (normal
  vs minimized) so the layout is identical and only button *states* change;
* among the runs that remain, take the **rightmost** one, because our button is
  by construction the last application button before the tray.

If the click still does not restore the window the harness falls back to the
Win32 API and records that explicitly, so a pass never silently depends on a
click that missed.

Usage:
    python accept_packaged_exe.py [--cycles N]

Run this with the **system** interpreter (``C:\\Program Files\\Develop\\Python\\
python.exe``), not whichever ``python`` is first on ``PATH``.  The harness
imports PIL through ``grab``, and the managed interpreter under
``~/.workbuddy-ai/binaries/python/`` does not ship it - there the import fails
with ``ModuleNotFoundError: No module named 'PIL'`` before any window is
touched.  (The interpreter is only needed to *drive* the harness; the
application under test is the packaged EXE and is independent of it.)
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
sys.path.insert(0, HERE)

import grab  # noqa: E402
import winapi as W  # noqa: E402
from PIL import Image, ImageChops, ImageStat  # noqa: E402

EXE = os.path.join(ROOT, "dist", "CodexConfigTool.exe")
OUT_DIR = os.path.join(HERE, "out")
# Overridable so a run against a second build (the Qt EXE) does not overwrite the
# Tk build's report - the two are meant to be compared side by side.
REPORT_PATH = os.path.join(OUT_DIR, "accept-packaged-report.json")
CYCLES = 5
WINDOW_WIDTH = 820
WINDOW_HEIGHT = 500
TITLE_BAR_HEIGHT = 38
# The title-bar buttons are 42 px wide canvases packed to the right in the order
# close, minimize, about; so the minimize button centre is right - 63.
MINIMIZE_BUTTON_OFFSET = 63
# Taskbar button strip: starts after the Start button, stops short of the clock
# (which changes every minute and would otherwise look like a very wide button).
TASKBAR_SCAN = (200, 1700)
BUTTON_MIN_WIDTH = 60
BUTTON_MAX_WIDTH = 400
DIFF_THRESHOLD = 24
MIN_CHANGED_PIXELS = 2
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.mouse_event.argtypes = (
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_void_p,
)
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

STILL_ACTIVE = 259


# --------------------------------------------------------------------------- #
# process / window discovery
# --------------------------------------------------------------------------- #
def process_alive(pid: int) -> bool:
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def existing_instance_pids(exe_name: str) -> list[int]:
    """PIDs of a running executable, matched by image name."""
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        cells = [cell.strip().strip('"') for cell in line.split('","')]
        if len(cells) >= 2 and cells[0].lower() == exe_name.lower():
            try:
                pids.append(int(cells[1]))
            except ValueError:
                continue
    return pids


def close_existing_instances(exe_name: str, notes: list[str]) -> int:
    """Kill every already-running copy so the single-instance mutex is free.

    The app takes a named mutex at startup.  If a copy is already running the new
    process only shows an "already running" message box (window class ``#32770``)
    and exits - so ``find_main_window`` never sees a ``TkTopLevel`` and the
    harness reports a confusing "main window not found" instead of the real cause.
    Killing first turns that into a clean start.

    Returns how many instances were closed.
    """
    pids = existing_instance_pids(exe_name)
    if not pids:
        return 0
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    deadline = time.time() + 6.0
    while time.time() < deadline and existing_instance_pids(exe_name):
        time.sleep(0.2)
    notes.append(f"closed {len(pids)} pre-existing {exe_name} instance(s): {pids}")
    return len(pids)


APP_WINDOW_TITLE = "Codex 配置助手"
# Both front ends, so a stale instance of either is found and closed before a run.
# "Qt" is a prefix because the class embeds the Qt version (Qt6110QWindowIcon).
APP_WINDOW_CLASSES = ("TkTopLevel", "Qt")


def app_window_handles() -> list[tuple[int, int]]:
    """``(hwnd, pid)`` for every top-level window that looks like the app.

    Matching by image name is not enough: a source run is ``python.exe`` and a
    packaged run is ``CodexConfigTool.exe``, but both hold the same single-instance
    mutex, so either can lock the other out.  The window title is the real
    discriminator; the class list only keeps the scan narrow.
    """
    found: list[tuple[int, int]] = []
    for hwnd in all_visible_windows():
        if not any(class_matches(W.class_name(hwnd), prefix) for prefix in APP_WINDOW_CLASSES):
            continue
        if APP_WINDOW_TITLE not in W.window_text(hwnd):
            continue
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(owner))
        found.append((hwnd, owner.value))
    return found


def close_existing_app_windows(notes: list[str]) -> int:
    """Kill whatever process owns an existing app window, packaged or source.

    Returns how many processes were asked to close.
    """
    pids = sorted({pid for _hwnd, pid in app_window_handles() if pid})
    if not pids:
        return 0
    for pid in pids:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    deadline = time.time() + 6.0
    while time.time() < deadline and app_window_handles():
        time.sleep(0.2)
    notes.append(f"closed app window owner process(es): {pids}")
    return len(pids)


def all_visible_windows() -> list[int]:
    found: list[int] = []

    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


def class_matches(class_name: str, expected: str) -> bool:
    """Match a window class, allowing a prefix.

    The Qt build's top-level class embeds the Qt version
    (``Qt6110QWindowIcon`` / ``Qt6112QWindowIcon`` depending on which PySide6 is
    installed), so an exact match would silently stop working after a Qt upgrade
    and the harness would report "main window not found".  A prefix
    (``--window-class Qt``) survives that.
    """
    if not expected:
        return True
    return class_name == expected or class_name.startswith(expected)


def find_main_window(exclude: set[int], timeout: float = 40.0, window_class: str = "TkTopLevel"):
    """Locate the app's main window, ignoring windows that already existed.

    PyInstaller ``--onefile`` runs the real application in a child of the
    bootloader, so the window does not belong to ``Popen.pid``.  Matching by
    class and size alone can also pick up a stale instance, hence ``exclude``.
    Returns ``(hwnd, pid)``.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for hwnd in all_visible_windows():
            if hwnd in exclude or not class_matches(W.class_name(hwnd), window_class):
                continue
            _, _, width, height = W.window_rect(hwnd)
            if width >= 700 and height >= 400:
                owner = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                return hwnd, owner.value
        time.sleep(0.4)
    return 0, 0


# --------------------------------------------------------------------------- #
# input
# --------------------------------------------------------------------------- #
class InputUnavailable(RuntimeError):
    """Synthetic mouse input does not reach the desktop.

    ``SetCursorPos``/``SendInput`` can both report success while the cursor never
    moves (a disconnected or non-interactive session).  Every click would then
    land wherever the real cursor happens to be, which would make the app look
    broken.  The harness treats this as an environment verdict, not a failure.
    """


def cursor_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def move_cursor(x: int, y: int) -> None:
    """Move the cursor and confirm it actually arrived."""
    user32.SetCursorPos(x, y)
    time.sleep(0.08)
    actual = cursor_pos()
    if actual != (x, y):
        hint = "" if W.on_a_monitor(x, y) else f"; ({x}, {y}) is on no monitor"
        raise InputUnavailable(f"cursor stayed at {actual} instead of ({x}, {y}){hint}")


def describe_input_block() -> str:
    """Why synthetic input is being refused, as far as Windows will say.

    The bare "cursor parked at ..." message says *what* happened but not *why*,
    and the three causes look identical from the outside: the window station or
    desktop is not the interactive one, the workstation is locked, or some
    foreground process is swallowing the pointer.  Each has a different fix, so
    the pre-flight gathers the discriminating evidence up front rather than
    leaving the next person to rediscover it with ad-hoc probes.

    Measured on this machine during the round-four acceptance attempt, when the
    block was in force (2026-09-18):

    * ``SetCursorPos`` returned **0** with ``GetLastError`` **0** - a silent
      refusal, not an error code;
    * ``SendInput`` returned **1** (the event *was* accepted) and the cursor
      still did not move;
    * ``GetClipCursor`` reported the full desktop, so nothing was clamping it;
    * the window station was ``WinSta0`` and the desktop ``Default``, i.e. the
      interactive ones;
    * ``OpenInputDesktop`` succeeded, so the workstation was **not** locked;
    * the foreground window was a real application (AutoCAD 2024 with a drawing
      open), not a secure desktop.

    That combination rules out the harness and the sandbox: the same probe fails
    identically with the command sandbox disabled, so it is a host-level
    condition, and the build is not implicated.
    """
    notes: list[str] = []

    # Aim at the primary monitor's centre, never a blind offset from wherever the
    # cursor happens to be.  A ``+40, +40`` hop can land in the dead zone between
    # misaligned monitors, where Windows clamps the cursor - and then the
    # ``SetCursorPos -> 0`` reported below would be blamed on the block when it is
    # actually the probe's own fault.  That is the exact trap
    # ``input_injection_available`` documents; do not commit it here.
    before = cursor_pos()
    width, height = W.primary_monitor_size()
    target = (width // 2, height // 2)
    if abs(target[0] - before[0]) < 20 and abs(target[1] - before[1]) < 20:
        target = (width // 4, height // 4)
    ctypes.set_last_error(0)
    moved = user32.SetCursorPos(*target)
    err = ctypes.get_last_error()
    time.sleep(0.1)
    notes.append(
        f"SetCursorPos -> {int(moved)} (GetLastError {err})"
        if not moved
        else "SetCursorPos reported success"
    )
    user32.SetCursorPos(*before)

    clip = wintypes.RECT()
    if user32.GetClipCursor(ctypes.byref(clip)):
        # Compare against the *virtual* screen, not the primary monitor: on a
        # multi-monitor desktop the clip rectangle is normally the whole virtual
        # desktop (measured 0,0,3840,1149 with a 1920x1080 primary here), and
        # testing it against the primary size would report a clamp that is not
        # there - crying wolf in the one message a future reader has to trust.
        virtual = (
            user32.GetSystemMetrics(76),  # SM_XVIRTUALSCREEN
            user32.GetSystemMetrics(77),  # SM_YVIRTUALSCREEN
            user32.GetSystemMetrics(76) + user32.GetSystemMetrics(78),  # + width
            user32.GetSystemMetrics(77) + user32.GetSystemMetrics(79),  # + height
        )
        if (clip.left, clip.top, clip.right, clip.bottom) != virtual:
            notes.append(
                f"cursor clipped to {clip.left},{clip.top},{clip.right},{clip.bottom}"
                f" (virtual screen {virtual[0]},{virtual[1]},{virtual[2]},{virtual[3]})"
            )

    if not user32.OpenInputDesktop(0, False, 0x0100):  # DESKTOP_READOBJECTS
        notes.append("input desktop could not be opened (workstation likely locked)")

    fg = user32.GetForegroundWindow()
    if fg:
        cls = ctypes.create_unicode_buffer(256)
        title = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(fg, cls, 256)
        user32.GetWindowTextW(fg, title, 256)
        notes.append(f"foreground {cls.value} {title.value[:40]!r}")

    return "; ".join(notes)


def input_injection_available() -> tuple[bool, str]:
    """Pre-flight: can we actually move the cursor?

    Probe points are deliberately kept inside the primary monitor.  A blind
    ``+40, +40`` offset from wherever the cursor happens to sit walks straight
    into the dead zone between misaligned monitors, where Windows clamps the
    cursor and a perfectly healthy desktop gets misreported as unable to
    accept input.
    """
    before = cursor_pos()
    width, height = W.primary_monitor_size()
    for target in ((width // 2, height // 2), (width // 3, height // 3)):
        if abs(target[0] - before[0]) < 20 and abs(target[1] - before[1]) < 20:
            target = (width // 4, height // 4)
        user32.SetCursorPos(*target)
        time.sleep(0.12)
        after = cursor_pos()
        if after != target:
            return False, (
                f"cursor parked at {after}; requested {target} "
                f"(primary monitor {width}x{height}) -- {describe_input_block()}"
            )
    user32.SetCursorPos(*before)
    time.sleep(0.1)
    return True, "ok"


def wait_for_input_injection(timeout: float) -> tuple[bool, str]:
    """Poll until synthetic input works, or give up.

    Input injection on a shared desktop is intermittent: it can be available for
    a minute and then stop entirely.  Waiting is cheaper than re-running by hand.
    """
    deadline = time.time() + timeout
    detail = "not probed"
    while True:
        injectable, detail = input_injection_available()
        if injectable or time.time() >= deadline:
            return injectable, detail
        print(f"[wait] input injection unavailable ({detail}); retrying", flush=True)
        time.sleep(5)


def click(x: int, y: int) -> None:
    move_cursor(x, y)
    time.sleep(0.06)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.09)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)


def click_app(hwnd: int, x: int, y: int, label: str, notes: list[str]) -> bool:
    """Click a point that is supposed to belong to the app's own window.

    Synthetic input goes to whatever is topmost under the cursor, so an
    unrelated window sitting over that point would otherwise turn "the button
    did not work" into a false accusation.  The window is exposed first and the
    escalation is recorded.
    """
    ok, detail = W.ensure_clickable(hwnd, x, y)
    notes.append(f"{label} @({x},{y}): {detail}")
    click(x, y)
    if detail.startswith("pinned"):
        # Never leave the app above the taskbar: the taskbar is topmost too.
        W.pin_on_top(hwnd, False)
    return ok


def ensure_foreground(hwnd: int, notes: list[str], label: str) -> bool:
    """Bring the app to the foreground before capturing a taskbar baseline.

    A taskbar button only carries its "active" highlight while its window owns
    the foreground.  Capturing the baseline from a background window therefore
    produces a strip whose button is indistinguishable from its neighbours, and
    the normal/minimized diff finds nothing to latch onto.  That is exactly how
    an earlier version of the soak test produced a false "the app is broken"
    verdict, so the outcome is recorded whether or not it succeeds.
    """
    ok = W.make_foreground(hwnd)
    notes.append(f"{label}: foreground={ok} (fg={W.foreground_hwnd():#x}, want={hwnd:#x})")
    return ok


def click_taskbar_bbox(bbox, notes: list[str], label: str) -> bool:
    """Click the centre of a taskbar-strip bbox, translating to screen coords."""
    origin_x, origin_y, _, _ = grab.taskbar_rect()
    x = origin_x + (bbox[0] + bbox[2]) // 2
    y = origin_y + (bbox[1] + bbox[3]) // 2
    root = W.root_at(x, y)
    on_taskbar = W.class_name(root) in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "MSTaskListWClass"}
    notes.append(f"{label} @({x},{y}): taskbar={on_taskbar} top={W.describe_occluder(0, x, y)}")
    click(x, y)
    return on_taskbar


# --------------------------------------------------------------------------- #
# taskbar button detection
# --------------------------------------------------------------------------- #
def changed_runs(current_path: str, baseline_path: str, x_range: tuple[int, int]):
    """All contiguous runs of changed columns between two strips.

    Each run is ``{"x0", "x1", "width", "peak"}`` in strip coordinates, left to
    right.  Unlike a bounding box this keeps neighbouring buttons separate.
    """
    current = Image.open(current_path).convert("RGB")
    baseline = Image.open(baseline_path).convert("RGB")
    if current.size != baseline.size:
        return []
    left, right = x_range
    right = min(right, current.width)
    box = ImageChops.difference(
        current.crop((left, 0, right, current.height)),
        baseline.crop((left, 0, right, current.height)),
    ).convert("L")
    width, height = box.size
    pixels = box.load()

    active = []
    for x in range(width):
        changed = sum(1 for y in range(height) if pixels[x, y] > DIFF_THRESHOLD)
        active.append(changed >= MIN_CHANGED_PIXELS)

    runs = []
    start = None
    for x, is_active in enumerate(active + [False]):
        if is_active and start is None:
            start = x
        elif not is_active and start is not None:
            columns = range(start, x)
            peak = max(pixels[c, y] for c in columns for y in range(height))
            runs.append(
                {
                    "x0": start + left,
                    "x1": x - 1 + left,
                    "width": x - start,
                    "peak": peak,
                }
            )
            start = None
    return runs


def button_runs(runs):
    """Keep only runs whose width is plausible for a taskbar button."""
    return [r for r in runs if BUTTON_MIN_WIDTH <= r["width"] <= BUTTON_MAX_WIDTH]


def rightmost_button(runs):
    """The app's button is the last application button before the tray."""
    plausible = button_runs(runs)
    return plausible[-1] if plausible else None


def run_luminance(path: str, run: dict) -> float:
    """Mean brightness of a run's columns in a strip."""
    image = Image.open(path).convert("L")
    box = image.crop((run["x0"], 2, run["x1"] + 1, image.height - 2))
    return float(ImageStat.Stat(box).mean[0])


def app_button(runs, normal_path: str, minimized_path: str):
    """Pick the run belonging to the app's own taskbar button.

    The diff between the normal and minimized strips contains at least two runs:
    our button loses its "active" highlight, and whichever window becomes active
    gains one.  Ours is therefore the run that got *darker*, which identifies it
    by behaviour instead of by position.  ``rightmost_button`` is the fallback.
    """
    candidates = button_runs(runs)
    if not candidates:
        return None, {}
    scored = []
    for run in candidates:
        delta = run_luminance(normal_path, run) - run_luminance(minimized_path, run)
        scored.append((delta, run))
    scored.sort(key=lambda item: -item[0])
    deltas = {f"{r['x0']}-{r['x1']}": round(d, 1) for d, r in scored}
    best_delta, best = scored[0]
    if best_delta <= 0:
        return rightmost_button(runs), deltas
    return best, deltas


def bbox_of(run):
    return (run["x0"], 0, run["x1"], grab.taskbar_rect()[3] - 1)


def describe_runs(runs) -> str:
    if not runs:
        return "none"
    return " ".join(f"{r['x0']}-{r['x1']}({r['width']})" for r in runs)


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
class EnvironmentUnavailable(RuntimeError):
    """The desktop/shell cannot support a valid run."""


def settings_path() -> str:
    """Path to the app's settings file, resolved the way the app resolves it.

    ``codex_config_tool`` builds this from ``APPDATA``. Both it and an earlier
    version of this harness fell back to the home directory when ``APPDATA`` was
    unset - which is a trap, not a convenience: a harness started from a shell
    without ``APPDATA`` (a POSIX shim, for instance) then reads and writes
    ``~/CodexConfigTool/settings.json``, a file the app never touches in normal
    use, and leaves it behind. The run looks fine and has tested the wrong
    settings file. Refuse instead.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise EnvironmentUnavailable(
            "APPDATA is not set, so the settings directory cannot be resolved the way "
            "the application resolves it. Without it this run would read and write "
            "~/CodexConfigTool/settings.json - not the file the app uses - and would "
            "leave that stray file behind. Run this from a normal Windows shell "
            "(cmd.exe or PowerShell), not a POSIX shim."
        )
    return os.path.join(appdata, "CodexConfigTool", "settings.json")


def suppress_onboarding():
    """Make sure the onboarding dialog cannot cover the main window.

    Returns ``(original_bytes, touched)``.  The original content is kept in
    memory and written back verbatim; no file is ever copied aside or deleted,
    so an interrupted run cannot lose the user's settings.
    """
    path = settings_path()
    original = None
    if os.path.exists(path):
        with open(path, "rb") as handle:
            original = handle.read()
        try:
            data = json.loads(original.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict) and data.get("hide_onboarding"):
            return original, False
    else:
        data = {}

    os.makedirs(os.path.dirname(path), exist_ok=True)
    merged = dict(data) if isinstance(data, dict) else {}
    merged["hide_onboarding"] = True
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)
    return original, True


def restore_settings(original, touched: bool) -> None:
    if not touched:
        return
    path = settings_path()
    with open(path, "wb") as handle:
        handle.write(original if original is not None else b"{}")


def drag_window(hwnd: int, dx: int, dy: int, notes: list[str], label: str) -> dict:
    """Press on the title bar, move by ``(dx, dy)``, release; report what happened.

    Three details are deliberate, all measured rather than assumed:

    * **No preliminary click.** This is the one that matters. `click_app` performs a
      complete press+release, and on a window whose title strip calls
      ``startSystemMove()`` that press hands control to the OS's modal ``SC_MOVE``
      loop - so the click enters the loop and releases inside it, and the drag's own
      press then arrives while the loop is still winding down. No new move starts and
      the drag reports ``moved [0, 0]`` while every part of the input channel is
      healthy. Measured on the packaged Qt build: with the preliminary click **0/3**
      drags moved, without it **3/3**. A drag needs no preliminary click - its own
      press is the press - and ``ensure_clickable`` raises the window without
      clicking, so that is what is called instead. The Tk build never showed this
      because its title bar implements the drag by hand rather than handing it to the
      window manager.
    * **The 1 px nudge before the release.** A window that reads the cursor when it
      pumps (``startSystemMove``, or ``SC_MOVE``) can miss the final ``SetCursorPos``
      entirely, leaving drags 10-12 px short of the target. Stepping onto the target
      and back makes the last position one the loop has already seen.
    * **The foreground call.** A synthetic press on a background window is consumed as
      an activation, not a drag. Record the outcome so a future failure can be
      attributed rather than guessed at.
    """
    before = W.window_rect(hwnd)
    foreground = ensure_foreground(hwnd, notes, label)
    click_x = before[0] + 300
    click_y = before[1] + TITLE_BAR_HEIGHT // 2
    pressed, detail = W.ensure_clickable(hwnd, click_x, click_y)
    notes.append(f"{label} ensure_clickable (no click) @({click_x},{click_y}): {detail}")
    user32.SetCursorPos(click_x, click_y)
    time.sleep(0.15)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.12)
    for step in range(1, 13):
        move_cursor(click_x + dx * step // 12, click_y + dy * step // 12)
        time.sleep(0.03)
    time.sleep(0.15)
    target_x, target_y = click_x + dx, click_y + dy
    user32.SetCursorPos(target_x + 1, target_y + 1)
    time.sleep(0.08)
    user32.SetCursorPos(target_x, target_y)
    time.sleep(0.10)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.4)
    after = W.window_rect(hwnd)
    return {
        "label": label,
        "pressed": pressed,
        "foreground": foreground,
        "requested": [dx, dy],
        "moved": [after[0] - before[0], after[1] - before[1]],
        "client": list(W.client_rect(hwnd)),
        "frame": list(W.frame_thickness(hwnd)),
    }


def warm_up_drag(hwnd: int, notes: list[str]) -> dict:
    """Do one real drag-and-return before any drag is measured.

    A defensive measure, kept because it is cheap and the failure it guards against
    is expensive to diagnose: an opening drag that reports ``moved [0, 0]`` is
    ambiguous between "the input channel is not latched yet" and "the application
    cannot be dragged". The in-process harness measured the former - the first
    synthetic press of a session moved 0 px while the window was demonstrably
    foreground - so a warm-up is done here too.

    Note this is *not* what was wrong with the first version of this step. That was
    the preliminary click inside ``click_app``, which is a different mechanism
    entirely; see ``drag_window``. Removing the click is the fix, and the warm-up
    only makes the remaining failures less ambiguous. Returning to the start position
    means the measured drags still begin where the caller expects.
    """
    warm = drag_window(hwnd, 40, 20, notes, "drag-warmup")
    moved = warm["moved"]
    if moved != [0, 0]:
        drag_window(hwnd, -moved[0], -moved[1], notes, "drag-warmup-return")
    return warm



# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    global REPORT_PATH

    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=CYCLES)
    parser.add_argument(
        "--wait-input",
        type=float,
        default=0.0,
        help="seconds to wait for synthetic input to become available",
    )
    parser.add_argument(
        "--exe",
        default=EXE,
        help=(
            "EXE to test (default: the Tk build). "
            "Use this to accept the Qt build: --exe dist/CodexConfigTool-Qt.exe"
        ),
    )
    parser.add_argument(
        "--window-class",
        default="TkTopLevel",
        help=(
            "expected top-level window class; a prefix match is allowed, so "
            "--window-class Qt covers Qt6110QWindowIcon / Qt6112QWindowIcon"
        ),
    )
    parser.add_argument(
        "--report",
        default="",
        help="report JSON path (default: out/accept-packaged-report.json)",
    )
    args = parser.parse_args()

    exe = os.path.abspath(args.exe)
    if args.report:
        REPORT_PATH = os.path.abspath(args.report)

    os.makedirs(OUT_DIR, exist_ok=True)
    if not os.path.exists(exe):
        print("MISSING EXE " + exe)
        return 2

    # Resolved before anything else: if APPDATA is missing this run would touch a
    # settings file the app never uses, so there is nothing worth measuring.
    try:
        resolved_settings = settings_path()
    except EnvironmentUnavailable as error:
        print("ENVIRONMENT " + str(error))
        return 3

    report: dict = {
        "exe": exe,
        "window_class": args.window_class,
        "settings_path": resolved_settings,
        "cycles": [],
        "failures": [],
        "settings_touched": False,
        "interaction_notes": [],
    }
    notes: list[str] = report["interaction_notes"]

    # Fail fast when synthetic input cannot reach the desktop: otherwise every
    # click lands at the real cursor position and the app gets blamed for it.
    injectable, detail = wait_for_input_injection(args.wait_input)
    report["environment"] = {"input_injection": injectable, "detail": detail}
    if not injectable:
        report["valid"] = False
        print("ENVIRONMENT input injection unavailable: " + detail)
        return write_report(report, environment_failure=True)

    original_settings, settings_touched = suppress_onboarding()
    report["settings_touched"] = settings_touched

    baseline_path = os.path.join(OUT_DIR, "accept-baseline-taskbar.png")
    process = None
    app_pid = 0
    hwnd = 0
    cursor = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(cursor))

    try:
        pre_existing = set(all_visible_windows())
        grab.grab_taskbar_strip().save(baseline_path)

        process = subprocess.Popen([exe], cwd=ROOT)
        hwnd, app_pid = find_main_window(pre_existing, window_class=args.window_class)
        if not hwnd:
            report["failures"].append("main window not found")
            return write_report(report)
        report["hwnd"] = hex(hwnd)
        report["app_pid"] = app_pid
        report["launcher_pid"] = process.pid
        time.sleep(2.5)  # let the taskbar registration settle

        # --- requirement 1: exactly one title bar on open
        frame = W.frame_thickness(hwnd)
        client = W.client_rect(hwnd)
        report["open"] = {
            "describe": W.describe(hwnd),
            "frame": list(frame),
            "client": list(client),
            "has_caption": bool(W.get_style(hwnd) & W.WS_CAPTION),
        }
        if frame != (0, 0):
            report["failures"].append(f"open: native frame present {frame}")
        if list(client) != [WINDOW_WIDTH, WINDOW_HEIGHT]:
            report["failures"].append(f"open: client size {client}")

        # requirement 4: the Shell only treats a window as minimizable when it
        # carries WS_MINIMIZEBOX.  Without it the taskbar button is
        # activate-only, so clicking the icon never toggles minimize/restore -
        # even though the window answers SC_MINIMIZE correctly.
        style = W.get_style(hwnd)
        report["minimizable"] = {
            "style": hex(style),
            "WS_SYSMENU": bool(style & W.WS_SYSMENU),
            "WS_MINIMIZEBOX": bool(style & W.WS_MINIMIZEBOX),
            "WS_MAXIMIZEBOX": bool(style & W.WS_MAXIMIZEBOX),
            "WS_CAPTION": bool(style & W.WS_CAPTION),
            "system_menu": W.system_menu_report(hwnd),
        }
        menu_items = (report["minimizable"]["system_menu"] or {}).get("items") or {}
        report["minimizable"]["minimize_item"] = menu_items.get("Minimize")
        if not report["minimizable"]["WS_MINIMIZEBOX"]:
            report["failures"].append(
                "open: WS_MINIMIZEBOX missing - the Shell will treat the taskbar "
                "button as activate-only and clicking it will not minimize"
            )
        if menu_items.get("Minimize") != "enabled":
            report["failures"].append(
                f"open: system menu Minimize is {menu_items.get('Minimize')!r}, expected 'enabled'"
            )

        # requirement 4 (normal state): the button must exist before we touch it
        open_strip = os.path.join(OUT_DIR, "accept-cycle0-normal-taskbar.png")
        grab.grab_taskbar_strip().save(open_strip)
        open_runs = changed_runs(open_strip, baseline_path, TASKBAR_SCAN)
        open_button = rightmost_button(open_runs)
        report["open_taskbar_runs"] = describe_runs(open_runs)
        report["open_taskbar_button"] = list(bbox_of(open_button)) if open_button else None
        if not open_button:
            report["failures"].append(
                f"open: no taskbar button detected (runs: {describe_runs(open_runs)})"
            )
            return write_report(report)

        # --- requirement 2: drag the custom title bar
        # Warm up before measuring: the opening synthetic press of a session does not
        # latch, so measuring it reports a phantom "the window did not move" failure.
        report["drag_warmup"] = warm_up_drag(hwnd, notes)

        drag_report = []
        for index, (dx, dy) in enumerate(((150, 70), (-190, 110)), start=1):
            entry = drag_window(hwnd, dx, dy, notes, f"drag{index}")
            if entry["moved"] != [dx, dy]:
                # One recorded retry. A drag that moves 0 px on the first attempt is
                # nearly always the input channel, but a genuine breakage fails the
                # retry as well - and the retry is recorded, so this is an auditable
                # second chance rather than a silent one.
                first_moved = entry["moved"]
                retry = drag_window(hwnd, dx, dy, notes, f"drag{index}-retry")
                retry["retried"] = True
                retry["first_attempt_moved"] = first_moved
                entry = retry
            drag_report.append(entry)
            if not entry["pressed"]:
                report["failures"].append(
                    f"drag{index}: title bar not clickable, {notes[-1]}"
                )
            if entry["client"] != [WINDOW_WIDTH, WINDOW_HEIGHT]:
                report["failures"].append(f"drag{index}: client changed {entry['client']}")
            if entry["frame"] != [0, 0]:
                report["failures"].append(f"drag{index}: frame appeared {entry['frame']}")
            if entry["moved"] != [dx, dy]:
                report["failures"].append(
                    f"drag{index}: window moved {entry['moved']} instead of {[dx, dy]}"
                )
        report["drag"] = drag_report

        # --- requirements 3-6: minimize/restore cycles
        for index in range(1, args.cycles + 1):
            cycle: dict = {"cycle": index}

            # recover from a previous cycle that failed to restore
            if W.is_iconic(hwnd):
                W.restore_window(hwnd)
                time.sleep(0.6)

            normal_strip = os.path.join(OUT_DIR, f"accept-cycle{index}-normal-taskbar.png")
            ensure_foreground(hwnd, notes, f"cycle{index} baseline")
            grab.grab_taskbar_strip().save(normal_strip)

            before = W.window_rect(hwnd)
            cycle["normal"] = {
                "client": list(W.client_rect(hwnd)),
                "frame": list(W.frame_thickness(hwnd)),
                "iconic": W.is_iconic(hwnd),
            }
            if cycle["normal"]["iconic"]:
                report["failures"].append(f"cycle{index}: window was still minimized")

            # requirement 3: click the app's own minimize button
            if not click_app(
                hwnd,
                before[0] + before[2] - MINIMIZE_BUTTON_OFFSET,
                before[1] + TITLE_BAR_HEIGHT // 2,
                f"cycle{index} minimize",
                notes,
            ):
                report["failures"].append(
                    f"cycle{index}: minimize button not clickable, {notes[-1]}"
                )
            time.sleep(1.5)
            cycle["alive_after_minimize"] = process_alive(app_pid)
            cycle["minimized"] = {
                "iconic": W.is_iconic(hwnd),
                "visible": W.is_visible(hwnd),
                "client": list(W.client_rect(hwnd)),
                "frame": list(W.frame_thickness(hwnd)),
            }
            if not cycle["minimized"]["iconic"]:
                report["failures"].append(f"cycle{index}: window did not minimize")
            if not cycle["alive_after_minimize"]:
                report["failures"].append(f"cycle{index}: process died after minimize")

            # requirement 4 (minimized state): locate the button by state change
            minimized_strip = os.path.join(OUT_DIR, f"accept-cycle{index}-minimized-taskbar.png")
            grab.grab_taskbar_strip().save(minimized_strip)
            state_runs = changed_runs(minimized_strip, normal_strip, TASKBAR_SCAN)
            cycle["state_runs"] = describe_runs(state_runs)
            button, deltas = app_button(state_runs, normal_strip, minimized_strip)
            cycle["button_luminance_delta"] = deltas
            if button is None:
                button = open_button
            cycle["taskbar_button"] = list(bbox_of(button))
            if not button_runs(state_runs):
                report["failures"].append(
                    f"cycle{index}: no taskbar button while minimized"
                    f" (runs: {describe_runs(state_runs)})"
                )

            # requirements 5/6: restore by clicking the taskbar button
            candidates = list(reversed(button_runs(state_runs)))
            if not candidates:
                candidates = [button]
            attempts = []
            restored_via = None
            was_iconic = W.is_iconic(hwnd)
            for candidate in candidates[:4]:
                bbox = bbox_of(candidate)
                attempts.append(list(bbox))
                W.pin_on_top(hwnd, False)  # the taskbar must stay reachable
                click_taskbar_bbox(bbox, notes, f"cycle{index} restore")
                time.sleep(1.4)
                if was_iconic and not W.is_iconic(hwnd):
                    restored_via = "taskbar-click"
                    break
                if not was_iconic:
                    break
            if restored_via is None:
                # Never claim a click restored the window if it did not.
                W.restore_window(hwnd)
                time.sleep(0.8)
                restored_via = "api-fallback"
                report["failures"].append(
                    f"cycle{index}: taskbar click did not restore the window"
                )
            cycle["restore_attempts"] = attempts
            cycle["restored_via"] = restored_via

            client = W.client_rect(hwnd)
            frame = W.frame_thickness(hwnd)
            cycle["restored"] = {
                "client": list(client),
                "frame": list(frame),
                "iconic": W.is_iconic(hwnd),
                "has_caption": bool(W.get_style(hwnd) & W.WS_CAPTION),
            }
            cycle["alive_after_restore"] = process_alive(app_pid)
            cycle["restored_screenshot"] = os.path.join(OUT_DIR, f"accept-cycle{index}-restored.png")
            try:
                grab.grab_window(hwnd, margin=40).save(cycle["restored_screenshot"])
            except Exception as error:  # noqa: BLE001
                cycle["restored_screenshot_error"] = repr(error)

            if cycle["restored"]["iconic"]:
                report["failures"].append(f"cycle{index}: did not restore")
            if list(client) != [WINDOW_WIDTH, WINDOW_HEIGHT]:
                report["failures"].append(f"cycle{index}: client size {client} after restore")
            if frame != (0, 0):
                report["failures"].append(f"cycle{index}: native frame {frame} after restore")
            if cycle["restored"]["has_caption"]:
                report["failures"].append(f"cycle{index}: WS_CAPTION returned")
            if not cycle["alive_after_restore"]:
                report["failures"].append(f"cycle{index}: process died after restore")

            # requirement 4 (toggle): clicking the taskbar button while the window
            # is normal must minimize it, the way every other app behaves.  The
            # window has to own the foreground for the Shell to read the click as
            # "minimize this" rather than "activate this".
            ensure_foreground(hwnd, notes, f"cycle{index} toggle foreground")
            toggle_bbox = bbox_of(button)
            W.pin_on_top(hwnd, False)
            click_taskbar_bbox(toggle_bbox, notes, f"cycle{index} toggle")
            time.sleep(1.5)
            cycle["toggle_minimized"] = W.is_iconic(hwnd)
            cycle["alive_after_toggle"] = process_alive(app_pid)
            if not cycle["toggle_minimized"]:
                report["failures"].append(
                    f"cycle{index}: clicking the taskbar button while normal did "
                    "not minimize (taskbar button is activate-only)"
                )
            else:
                # click again to put it back for the next cycle
                W.pin_on_top(hwnd, False)
                click_taskbar_bbox(toggle_bbox, notes, f"cycle{index} toggle-restore")
                time.sleep(1.4)
                cycle["toggle_restored"] = not W.is_iconic(hwnd)
                if not cycle["toggle_restored"]:
                    report["failures"].append(
                        f"cycle{index}: a second taskbar click did not restore"
                    )
                    W.restore_window(hwnd)
                    time.sleep(0.8)
                toggle_client = list(W.client_rect(hwnd))
                toggle_frame = list(W.frame_thickness(hwnd))
                cycle["toggle_geometry"] = {"client": toggle_client, "frame": toggle_frame}
                if toggle_client != [WINDOW_WIDTH, WINDOW_HEIGHT]:
                    report["failures"].append(
                        f"cycle{index}: client {toggle_client} after the toggle"
                    )
                if toggle_frame != [0, 0]:
                    report["failures"].append(
                        f"cycle{index}: native frame {toggle_frame} after the toggle"
                    )

            report["cycles"].append(cycle)
            print("[cycle] " + json.dumps(cycle, ensure_ascii=False))
    except InputUnavailable as error:
        report["valid"] = False
        report["environment"] = {"input_injection": False, "detail": str(error)}
        print("ENVIRONMENT input injection lost mid-run: " + str(error))
        return write_report(report, environment_failure=True)
    finally:
        user32.SetCursorPos(cursor.x, cursor.y)
        if hwnd:
            try:
                W.pin_on_top(hwnd, False)
            except Exception:  # noqa: BLE001
                pass
        for pid in {process.pid if process else 0, app_pid}:
            if pid:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )
        restore_settings(original_settings, settings_touched)

    return write_report(report)


def write_report(report: dict, environment_failure: bool = False) -> int:
    path = REPORT_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print("REPORT " + path)
    if environment_failure:
        verdict = "INVALID (environment)"
    elif report.get("failures"):
        verdict = "FAIL"
    else:
        verdict = "PASS"
    print(
        "SUMMARY "
        + json.dumps(
            {
                "verdict": verdict,
                "cycles": len(report.get("cycles", [])),
                "failures": report.get("failures", []),
                "environment": report.get("environment"),
            },
            ensure_ascii=False,
        )
    )
    if environment_failure:
        return 3
    return 0 if not report.get("failures") else 1


if __name__ == "__main__":
    raise SystemExit(main())
