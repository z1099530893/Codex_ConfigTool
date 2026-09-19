"""Drive the *shipping* Qt window with synthetic input and check it against the
seven standing window requirements, while it is running.

Why this file exists
--------------------
``proto_restore_flash.py`` proves the flicker is gone, but it can only do that
because the window stays open for the whole run - which means it never touches
the *interaction* surface.  Everything the Tk build was verified for (drag,
minimise-only, taskbar button, restore, fixed size) was checked by scripts that
drive Tk's own event loop.  The Qt build has had a structural smoke test
(``smoke_qt_app.py``) and a visual tour (``qt_visual_tour.py``) but never a
single real mouse event.

So this script is the missing half.  It runs the real window and:

  R1  custom title bar, no native frame          style bits + frame thickness
  R2  dragging the title bar does not tear       synthetic drag + mid-drag capture
  R3  minimise only, never maximise              style bits, system menu, SC_MAXIMIZE
  R4  a taskbar button in every state            taskbar strip pixels + shell query
  R5  no second title bar after restore          style bits + top-band pixels
  R6  the window stays 820x500                   client rect after every stage
  R7  config management does not regress         real slots and real dialogs

Two techniques, deliberately different
--------------------------------------
Window-level checks use **synthetic input** (``SetCursorPos`` + ``mouse_event``),
because that is the only way to prove the window behaves under a real mouse.
Functional checks call the application's **own slots**, because what is being
tested there is the ported logic, not Qt's ability to deliver a click - and a
modal ``exec()`` would deadlock a test that has to wait for the GUI thread.

Threading note: synthetic input must be injected from a worker thread.  Qt's
``startSystemMove`` (or the ``SC_MOVE`` modal loop it posts) runs *on the GUI
thread*, so injecting from a ``QTimer`` callback would block inside
``mouse_event(LEFTDOWN)`` and never reach ``LEFTUP``.  GUI-side assertions are
marshalled back with ``CodexConfigWindow.post``.

Every persisted path is redirected by ``sandbox_env`` before the window is
built: an earlier ad-hoc probe of this kind overwrote the real ``settings.json``
twice by forgetting that.

Usage:
    python verify_qt_app.py
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import io
import json
import os
import sys
import threading
import time
from contextlib import redirect_stderr
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import sandbox_env  # noqa: E402

# Must happen before any window is constructed.
SANDBOX, CONFIG_DIR = sandbox_env.isolate("codex-verify-qt-")

import grab  # noqa: E402
import winapi as W  # noqa: E402
from accept_packaged_exe import (  # noqa: E402
    TASKBAR_SCAN,
    InputUnavailable,
    app_button,
    bbox_of,
    changed_runs,
    click_taskbar_bbox,
    describe_runs,
    ensure_foreground,
    wait_for_input_injection,
)

import codex_config_tool as core  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import codex_config_qt as view  # noqa: E402

OUT_DIR = os.path.join(HERE, "out")
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

CYCLES = 5
DRAG_STEPS = 16
DRAG_CAPTURE_AT = 7
# Qt's frameGeometry is stable, but the shell may nudge a window by a pixel or
# two when it lands against a screen edge, so allow a small error.
DRAG_TOLERANCE = 8
# Mean absolute luminance difference between the settled window and a capture
# taken mid-drag.  A torn or stale frame reads in the tens; a clean one in the
# low single digits.
TEAR_THRESHOLD = 3.0
# Mean luminance of the top 38 px.  The custom title bar is #000000 with a few
# light glyphs; a native grey caption reads 200+.
TITLE_BAND_MAX = 70.0

user32 = ctypes.windll.user32
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = ctypes.c_bool
user32.mouse_event.argtypes = (
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_void_p,
)

CHECKS: list[dict] = []
ARTIFACTS: list[str] = []
DRAGS: list[dict] = []
CYCLES_LOG: list[dict] = []
FUNCTIONAL: dict = {}
CREATED_DIALOGS: list[dict] = []
CALLS: list[dict] = []


# --------------------------------------------------------------------------
# reporting helpers
# --------------------------------------------------------------------------


def check(name: str, ok: bool, detail: str = "", environment: bool = False) -> bool:
    """Record one check.

    ``environment=True`` marks a check that could not be *evaluated* because the
    desktop refused synthetic input, rather than because the code is wrong -
    ``SetCursorPos`` gets clamped a few pixels short near the screen edge and the
    shared desktop stops accepting injected input at unpredictable moments.  The
    same convention as ``accept_packaged_exe.py``'s ``InputUnavailable``: report
    it separately and do not fail the run on it.
    """
    entry = {"name": name, "ok": bool(ok), "detail": detail, "environment": bool(environment)}
    CHECKS.append(entry)
    tag = "ENV " if environment else ("PASS" if ok else "FAIL")
    print(f"[{tag}] {name}" + (f"  -- {detail}" if detail else ""))
    return bool(ok)


def artifact(path: str) -> str:
    ARTIFACTS.append(path)
    return path


def record_call(name: str):
    def record(*args, **kwargs):
        CALLS.append(
            {
                "call": name,
                "args": [repr(item)[:140] for item in args],
                "kwargs": {key: repr(value)[:100] for key, value in kwargs.items()},
            }
        )

    return record


def calls_to(name: str) -> list[dict]:
    return [item for item in CALLS if item["call"] == name]


def _luminance(image) -> float:
    data = list(image.convert("L").getdata())
    return sum(data) / max(len(data), 1)


def _tear_score(reference, current) -> tuple[float, int]:
    """Mean/max absolute difference, ignoring a border of compositor effects."""
    from PIL import ImageChops

    if reference.size != current.size:
        return 999.0, 255
    pad = 12
    box = (pad, pad, reference.width - pad, reference.height - pad)
    diff = ImageChops.difference(reference.crop(box), current.crop(box)).convert("L")
    data = list(diff.getdata())
    return sum(data) / max(len(data), 1), max(data)


# --------------------------------------------------------------------------
# synthetic input
# --------------------------------------------------------------------------


def drag(hwnd: int, start_x: int, start_y: int, dx: int, dy: int) -> dict:
    """Press on the title strip, walk the cursor, release.

    Returns the mid-drag capture, because the capture has to be compared against
    a settled reference of the same window.

    Two details are about the *injection*, not the app.  ``startSystemMove``
    hands the drag to the OS's own ``SC_MOVE`` loop, which reads the cursor
    position when it pumps - so a ``SetCursorPos`` can be missed entirely.  That
    showed up as drags landing 10-12 px short of the target, and once as a drag
    that moved the window 0 px.  Nudging one pixel past the target and back
    before releasing guarantees the final position is processed.
    """
    user32.SetCursorPos(start_x, start_y)
    time.sleep(0.20)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.20)

    mid = None
    for index in range(1, DRAG_STEPS + 1):
        user32.SetCursorPos(start_x + dx * index // DRAG_STEPS, start_y + dy * index // DRAG_STEPS)
        if index == DRAG_CAPTURE_AT:
            time.sleep(0.06)
            # Captured mid-move, with the button still down, so a torn or stale
            # frame is what ends up in the image.
            mid = grab.grab_window(hwnd)
        time.sleep(0.035)

    target_x, target_y = start_x + dx, start_y + dy
    user32.SetCursorPos(target_x + 1, target_y + 1)
    time.sleep(0.08)
    user32.SetCursorPos(target_x, target_y)
    time.sleep(0.10)

    time.sleep(0.25)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    time.sleep(0.40)
    return {"mid": mid}


def capture_window(hwnd: int, tag: str) -> tuple[object, str]:
    """Capture exactly the window's screen area.

    ``W.window_rect`` returns ``(left, top, width, height)`` - it is not a RECT -
    so never compute ``right - left`` from it.  ``grab.grab_window`` reads the
    real ``GetWindowRect`` itself.  (Getting this wrong is invisible until the
    tear and title-band numbers come out absurd, which is how it was caught.)
    """
    image = grab.grab_window(hwnd)
    path = artifact(os.path.join(OUT_DIR, f"verify-qt-{tag}.png"))
    image.save(path)
    return image, path


def taskbar_strip(tag: str) -> str:
    """Capture the real taskbar and return the saved path."""
    strip = grab.grab_taskbar_strip()
    path = artifact(os.path.join(OUT_DIR, f"verify-qt-taskbar-{tag}.png"))
    strip.save(path)
    return path


# --------------------------------------------------------------------------
# sandbox
# --------------------------------------------------------------------------


def seed_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    core.write_text(
        CONFIG_DIR / "config.toml",
        core.build_fresh_config_toml("sk-verify-seed", core.DEFAULT_PROVIDER, core.DEFAULT_BASE_URL),
    )
    core.update_auth_json(CONFIG_DIR / "auth.json", "sk-verify-seed")
    return CONFIG_DIR


def install_modal_recorders() -> None:
    """Make every modal dialog constructible but non-blocking, and observable."""

    def wrap(name: str, cls) -> None:
        original_init = cls.__init__

        def __init__(self, *args, **kwargs):  # noqa: N807
            entry = {
                "dialog": name,
                "args": [type(item).__name__ for item in args],
                "arg_repr": [repr(item)[:80] for item in args],
            }
            try:
                original_init(self, *args, **kwargs)
            except BaseException as exc:  # noqa: BLE001
                entry["error"] = f"{type(exc).__name__}: {exc}"
                CREATED_DIALOGS.append(entry)
                return
            CREATED_DIALOGS.append(entry)

        cls.__init__ = __init__
        for method in ("exec", "run"):
            if hasattr(cls, method):
                setattr(cls, method, lambda self, *a, **k: 0)

    for name in (
        "MessageDialog",
        "ConfigNameDialog",
        "ScanPickerDialog",
        "OnboardingDialog",
        "DonationDialog",
        "AboutDialog",
        "ProfileEditorDialog",
    ):
        wrap(name, getattr(view, name))


def created(name: str) -> list[dict]:
    return [item for item in CREATED_DIALOGS if item["dialog"] == name]


# --------------------------------------------------------------------------
# the driver
# --------------------------------------------------------------------------


class Driver:
    def __init__(self, app: QApplication, window: view.CodexConfigWindow) -> None:
        self.app = app
        self.window = window
        self.hwnd = 0
        self.errors: list[str] = []
        self.environment_errors: list[str] = []
        self.input_ok = False
        self.input_detail = "not probed"

    # -- GUI marshalling ---------------------------------------------------

    def on_gui(self, fn, timeout: float = 25.0):
        box: dict = {}
        done = threading.Event()

        def call() -> None:
            try:
                box["value"] = fn()
            except BaseException as exc:  # noqa: BLE001
                box["error"] = exc
            finally:
                done.set()

        self.window.post(call)
        if not done.wait(timeout):
            raise TimeoutError("GUI thread did not answer in time")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    # -- stages ------------------------------------------------------------

    def stage_frame(self) -> None:
        hwnd = self.hwnd
        style = W.get_style(hwnd)
        exstyle = W.get_ex_style(hwnd)
        frame = W.frame_thickness(hwnd)
        client = W.client_rect(hwnd)
        print("[frame] " + W.describe(hwnd))

        check(
            "R1 无原生标题栏（WS_CAPTION 未设置）",
            not (style & W.WS_CAPTION),
            f"style={style:#010x} exstyle={exstyle:#010x}",
        )
        check(
            "R1 无原生可调整边框（WS_THICKFRAME 未设置）",
            not (style & W.WS_THICKFRAME),
            f"style={style:#010x}",
        )
        check("R1 非客户区边框厚度为 0", tuple(frame) == (0, 0), f"frame={tuple(frame)}")
        check(
            "R6 初始客户区为 820x500",
            list(client) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT],
            f"client={list(client)}",
        )

        menu = W.system_menu_report(hwnd)
        FUNCTIONAL["system_menu"] = menu
        maximize = (menu.get("items") or {}).get("maximize")
        check(
            "R3 系统菜单里的“最大化”不可用",
            maximize in (None, "absent") or "GRAYED" in maximize or "DISABLED" in maximize,
            f"maximize={maximize!r}",
        )
        check("R3 有 WS_MINIMIZEBOX（任务栏可切换）", bool(style & W.WS_MINIMIZEBOX), "")

    def stage_drag(self) -> None:
        hwnd = self.hwnd
        saved = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(saved))

        W.make_foreground(hwnd)
        self.on_gui(lambda: (self.window.raise_(), self.window.activateWindow()))
        time.sleep(0.5)

        # Pre-flight before any measured drag.  Synthetic input on a shared
        # desktop is intermittent, and a drag injected while the cursor cannot
        # be moved produces numbers that look like UI failures but are not: the
        # press lands on whatever window is in front, so the window does not
        # move, the tear capture shows that other window, and the diff explodes.
        # That is exactly how one whole run came out as four bogus drag failures.
        if not self.input_ok:
            check(
                "R2 拖动验证（合成输入不可用，本次无法评估）",
                False,
                self.input_detail,
                environment=True,
            )
            return

        # The first synthetic press of a session does not engage the OS move
        # loop at all - measured: the first measured drag moved the window 0 px,
        # and a zero-delta warm-up did not help either.  Warm up with a drag that
        # really moves, then drag back, so the measured drags start from a loop
        # that has already latched on.  Discarded, not checked.
        foreground_before = W.make_foreground(hwnd, timeout=5.0)
        warm = W.window_rect(hwnd)
        drag(hwnd, warm[0] + 300, warm[1] + 19, 40, 20)
        moved = W.window_rect(hwnd)
        drag(hwnd, moved[0] + 300, moved[1] + 19, -40, -20)
        time.sleep(0.4)
        FUNCTIONAL["drag_foreground"] = {
            "foreground_before_warmup": foreground_before,
            "foreground_after_warmup": W.foreground_hwnd() == hwnd,
            "warmup_moved_window": tuple(W.window_rect(hwnd)) != tuple(warm),
        }

        reference, reference_path = capture_window(hwnd, "at-rest")
        print(f"[drag] reference {reference_path}")

        plans = ((180, 90), (-260, 140), (120, -200), (0, 0))
        try:
            for index, (dx, dy) in enumerate(plans, start=1):
                if W.foreground_hwnd() != hwnd:
                    W.make_foreground(hwnd, timeout=5.0)
                    time.sleep(0.3)
                foreground = W.foreground_hwnd() == hwnd
                before = W.window_rect(hwnd)
                start_x = before[0] + 300  # inside the 38 px black strip, away from the buttons
                start_y = before[1] + 19
                result = drag(hwnd, start_x, start_y, dx, dy)
                after = W.window_rect(hwnd)
                moved = (after[0] - before[0], after[1] - before[1])
                client = W.client_rect(hwnd)
                frame = W.frame_thickness(hwnd)
                style = W.get_style(hwnd)

                expected = (0, 0) if (dx, dy) == (0, 0) else None
                moved_ok = (
                    abs(moved[0]) <= DRAG_TOLERANCE and abs(moved[1]) <= DRAG_TOLERANCE
                    if expected is not None
                    else abs(moved[0] - dx) <= DRAG_TOLERANCE
                    and abs(moved[1] - dy) <= DRAG_TOLERANCE
                )
                # A drag only proves something about tearing if it actually
                # happened, so the tear measurement is gated on this.
                dragged = foreground and moved_ok

                entry = {
                    "drag": index,
                    "requested": [dx, dy],
                    "moved": list(moved),
                    "client": list(client),
                    "frame": list(frame),
                    "has_caption": bool(style & W.WS_CAPTION),
                    "iconic": W.is_iconic(hwnd),
                    "foreground": foreground,
                    "dragged": dragged,
                }

                check(
                    f"R2 第{index}次拖动：合成输入确实拖到了窗口",
                    dragged,
                    f"foreground={foreground} moved={list(moved)} requested={[dx, dy]}",
                    environment=(not foreground),
                )

                if result["mid"] is not None:
                    mid_path = artifact(os.path.join(OUT_DIR, f"verify-qt-drag{index}-mid.png"))
                    result["mid"].save(mid_path)
                    mean, peak = _tear_score(reference, result["mid"])
                    entry.update({"tear_mean": round(mean, 3), "tear_peak": peak, "mid": mid_path})
                    check(
                        f"R2 第{index}次拖动：拖动中画面无撕裂",
                        mean < TEAR_THRESHOLD,
                        f"diff_mean={mean:.3f} peak={peak} (<{TEAR_THRESHOLD})"
                        + ("" if dragged else "; 拖动未发生，此读数无意义"),
                        environment=(not dragged),
                    )
                else:
                    check(
                        f"R2 第{index}次拖动：取到拖动中的画面",
                        False,
                        "no mid-drag capture",
                        environment=(not foreground),
                    )

                check(
                    f"R2 第{index}次拖动：尺寸保持 820x500 且无原生边框",
                    list(client) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT]
                    and tuple(frame) == (0, 0)
                    and not (style & W.WS_CAPTION),
                    f"client={list(client)} frame={list(frame)} caption={bool(style & W.WS_CAPTION)}",
                )
                DRAGS.append(entry)
                print("[drag] " + json.dumps(entry, ensure_ascii=False))
        finally:
            user32.SetCursorPos(saved.x, saved.y)

    def stage_maximize(self) -> None:
        """Requirement 3: minimise only.

        Three layers, because the first two are not enough on their own:

        * ``WS_MAXIMIZEBOX`` unset      -> no maximise button, no menu entry
        * system menu has no maximise   -> the jump list offers none either
        * ``nativeEvent`` refuses ``SC_MAXIMIZE`` -> Win+Up does nothing

        The third exists because the first two do **not** cover it:
        ``DefWindowProc`` honours ``SC_MAXIMIZE`` whatever the style says, and
        ``probe_sc_maximize.py`` measured the Tk build resizing to 1920x1080 and
        an unguarded Qt window to 1920x1040.  This is the one requirement the
        port implements more strictly than the build it replaces.
        """
        hwnd = self.hwnd
        before = W.window_rect(hwnd)

        # The realistic path: Win+Up reaches the window as WM_SYSCOMMAND.
        user32.SendMessageW(hwnd, W.WM_SYSCOMMAND, W.SC_MAXIMIZE, 0)
        time.sleep(0.5)
        after_command = W.window_rect(hwnd)
        client_command = W.client_rect(hwnd)
        check(
            "R3 SC_MAXIMIZE（Win+Up 的路径）不改变窗口尺寸",
            list(client_command) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT]
            and tuple(after_command) == tuple(before),
            f"before={list(before)} after={list(after_command)} client={list(client_command)}",
        )

        # The blunt path: ShowWindow(SW_SHOWMAXIMIZED).  Reported, not asserted
        # twice - if the shell refuses to honour it either, so much the better.
        user32.ShowWindow(hwnd, W.SW_SHOWMAXIMIZED)
        time.sleep(0.6)
        client_show = W.client_rect(hwnd)
        FUNCTIONAL["show_maximized_client"] = list(client_show)
        check(
            "R3 ShowWindow(SW_SHOWMAXIMIZED) 也不改变窗口尺寸",
            list(client_show) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT],
            f"client={list(client_show)}",
        )

        W.restore_window(hwnd)
        time.sleep(0.5)
        self.on_gui(lambda: self.window.showNormal())
        time.sleep(0.4)
        check(
            "R3 最大化尝试之后窗口仍是 820x500",
            list(W.client_rect(hwnd)) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT],
            f"client={list(W.client_rect(hwnd))}",
        )

    def stage_taskbar(self) -> None:
        """Find our taskbar button, then click it - both halves of the contract.

        ``window foreground + click its button -> minimise`` and
        ``window minimized + click its button -> restore`` are the exact
        behaviour the user originally filed the bug about, and neither can be
        inferred from style bits.

        The button is located *by behaviour* rather than by position: two strips
        captured moments apart with the layout identical (normal vs minimized)
        differ only in which button carries the "active" highlight, and ours is
        the run that got darker.  A strip captured with the window hidden is
        useless as a baseline on this machine - the taskbar repacks its buttons
        and its widgets animate, so a whole-width diff finds nothing useful.
        """
        hwnd = self.hwnd
        notes: list[str] = []
        result: dict = {"notes": notes}

        # No second pre-flight: the run-level probe already ran, and each click
        # below reports its own refusal if the desktop stops cooperating later.
        result["input_injection"] = {"available": self.input_ok, "detail": self.input_detail}

        self.on_gui(lambda: self.window.showNormal())
        time.sleep(0.5)
        ensure_foreground(hwnd, notes, "normal")
        time.sleep(0.8)
        normal_path = taskbar_strip("normal")

        self.on_gui(lambda: self.window._minimize_window())  # noqa: SLF001
        time.sleep(1.1)
        minimized_path = taskbar_strip("minimized")

        runs = changed_runs(minimized_path, normal_path, TASKBAR_SCAN)
        button, deltas = app_button(runs, normal_path, minimized_path)
        result.update(
            {
                "normal_strip": normal_path,
                "minimized_strip": minimized_path,
                "runs": runs,
                "runs_text": describe_runs(runs),
                "button": button,
                "luminance_deltas": deltas,
                "would_appear_in_taskbar": W.would_appear_in_taskbar(hwnd),
            }
        )
        print("[taskbar] " + json.dumps(result, ensure_ascii=False))

        check(
            "R4 任务栏上存在本程序的按钮（按状态差异定位）",
            button is not None,
            f"runs={describe_runs(runs)} deltas={deltas}",
        )
        check(
            "R4 最小化状态下窗口仍会出现在任务栏（Shell 规则）",
            W.would_appear_in_taskbar(hwnd),
            f"style={W.get_style(hwnd):#010x} exstyle={W.get_ex_style(hwnd):#010x}",
        )
        if button is None:
            W.restore_window(hwnd)
            time.sleep(0.6)
            self.on_gui(lambda: self.window.showNormal())
            FUNCTIONAL["taskbar"] = result
            return

        bbox = bbox_of(button)

        def click(label: str) -> str:
            """Click the taskbar button; report an environment refusal as such."""
            try:
                click_taskbar_bbox(bbox, notes, label)
                return "ok"
            except InputUnavailable as exc:
                result.setdefault("input_verdicts", []).append(f"{label}: {exc}")
                return "unavailable"

        # -- half one: minimized + click the button -> restore ----------------
        verdict_restore = click("restore")
        time.sleep(1.0)
        self.on_gui(lambda: self.window.showNormal())
        time.sleep(0.4)
        if verdict_restore == "unavailable":
            # Keep the run going on the API path so the later stages still mean
            # something; the click itself is reported as unevaluated.
            W.restore_window(hwnd)
            time.sleep(0.6)
        restored_iconic = W.is_iconic(hwnd)
        result["click_to_restore_iconic"] = restored_iconic
        check(
            "R4 最小化时点击任务栏图标会恢复窗口",
            restored_iconic is False,
            f"iconic={restored_iconic}; verdict={verdict_restore}; "
            f"notes={notes[-1] if notes else ''}",
            environment=(verdict_restore == "unavailable"),
        )
        check(
            "R6 任务栏恢复后仍是 820x500",
            list(W.client_rect(hwnd)) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT],
            f"client={list(W.client_rect(hwnd))}",
        )

        # -- half two: normal + foreground + click the button -> minimise -----
        ensure_foreground(hwnd, notes, "toggle")
        time.sleep(0.8)
        verdict_minimize = click("minimize")
        time.sleep(1.0)
        toggled_iconic = W.is_iconic(hwnd)
        result["click_to_minimize_iconic"] = toggled_iconic
        check(
            "R4 前台时点击任务栏图标会最小化窗口",
            toggled_iconic is True,
            f"iconic={toggled_iconic}; verdict={verdict_minimize}; "
            f"notes={notes[-1] if notes else ''}",
            environment=(verdict_minimize == "unavailable"),
        )

        # Leave the window normal for the rest of the run.
        click("restore-again")
        time.sleep(1.0)
        W.restore_window(hwnd)
        time.sleep(0.5)
        self.on_gui(lambda: self.window.showNormal())
        time.sleep(0.4)
        result["final_iconic"] = W.is_iconic(hwnd)

        FUNCTIONAL["taskbar"] = result

    def stage_cycles(self) -> None:
        hwnd = self.hwnd
        for cycle in range(1, CYCLES + 1):
            self.on_gui(lambda: self.window._minimize_window())
            time.sleep(0.85)
            iconic = W.is_iconic(hwnd)
            check(f"R4 第{cycle}次：最小化按钮后 IsIconic", iconic, f"iconic={iconic}")
            check(
                f"R4 第{cycle}次：最小化状态下仍会出现在任务栏",
                W.would_appear_in_taskbar(hwnd),
                f"style={W.get_style(hwnd):#010x}",
            )

            W.restore_window(hwnd)
            time.sleep(0.85)
            self.on_gui(lambda: self.window.showNormal())
            time.sleep(0.35)
            # Confirm the restore actually took before capturing: a screen grab
            # of a still-minimised window reads whatever is behind it, which is
            # how an earlier run produced a nonsensical "title band" reading.
            if W.is_iconic(hwnd):
                W.restore_window(hwnd)
                self.on_gui(lambda: self.window.showNormal())
                time.sleep(0.4)
            iconic_after = W.is_iconic(hwnd)

            style = W.get_style(hwnd)
            frame = W.frame_thickness(hwnd)
            client = W.client_rect(hwnd)
            children = W._descendants(hwnd)  # noqa: SLF001 - reuse the census helper
            image, shot = capture_window(hwnd, f"restore{cycle}")
            band = _luminance(image.crop((0, 0, image.width, 38)))

            entry = {
                "cycle": cycle,
                "iconic_before": iconic,
                "iconic_after": iconic_after,
                "client": list(client),
                "frame": list(frame),
                "has_caption": bool(style & W.WS_CAPTION),
                "native_children": len(children),
                "title_band_luminance": round(band, 2),
                "screenshot": shot,
            }
            CYCLES_LOG.append(entry)
            print("[cycle] " + json.dumps(entry, ensure_ascii=False))

            check(
                f"R5 第{cycle}次：恢复后窗口真的回到屏幕且可见",
                not iconic_after and W.is_visible(hwnd),
                f"iconic={iconic_after} visible={W.is_visible(hwnd)}",
            )
            check(
                f"R5 第{cycle}次：恢复后没有第二个标题栏",
                not (style & W.WS_CAPTION) and tuple(frame) == (0, 0) and band < TITLE_BAND_MAX,
                f"caption={bool(style & W.WS_CAPTION)} frame={list(frame)} band={band:.1f}",
            )
            check(
                f"R5 第{cycle}次：恢复后没有多出来的原生子窗口",
                len(children) == 0,
                f"native_children={len(children)}",
            )
            check(
                f"R6 第{cycle}次：恢复后仍为 820x500",
                list(client) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT],
                f"client={list(client)}",
            )

    def stage_functional(self) -> None:
        window = self.window
        result: dict = {}

        # -- 当前配置页 ----------------------------------------------------
        self.on_gui(lambda: window.show_page("current"))
        time.sleep(0.2)
        result["current_page"] = self.on_gui(
            lambda: {
                "active_page": window.active_page,
                # The current page has no "pageTitle" heading; its header is a
                # status dot plus the active profile name plus a welcome line.
                "name_object_name": window.current_name_label.objectName(),
                "welcome_present": any(
                    "欢迎使用" in label.text()
                    for label in window.pages["current"].findChildren(type(window.current_name_label))
                ),
                "nav_checked": [key for key, item in window.nav_items.items() if item.isChecked()],
                "path_edit": window.path_edit.text(),
                "current_path": str(window.current_path()),
                "path_edit_readonly": window.path_edit.isReadOnly(),
                "key_echo_is_password": window.key_entry.echoMode().name,
                "provider_field": window.provider_field.text(),
                "base_url_field": window.base_url_field.text(),
                "model_field": window.model_field.text(),
                "current_name": window.current_name_label.text(),
            }
        )
        page = result["current_page"]
        # Evaluated one condition at a time: a combined boolean in a failure
        # detail says *that* it failed, never *which* part.  The path is
        # canonicalized before comparing because the app does the same thing to
        # every path it is handed.
        page_conditions = {
            "nav_highlights_current_only": page["nav_checked"] == ["current"],
            "path_edit_shows_sandbox_dir": page["path_edit"]
            == str(core.canonical_config_path(CONFIG_DIR)),
            "path_edit_is_readonly": page["path_edit_readonly"],
            "name_label_object_name": page["name_object_name"] == "currentName",
            "welcome_line_present": page["welcome_present"],
        }
        page["conditions"] = page_conditions
        check(
            "R7 当前配置页：导航高亮、路径回填、欢迎文案",
            all(page_conditions.values()),
            json.dumps(page, ensure_ascii=False),
        )
        check(
            "R7 当前配置页：API Key 默认打码",
            result["current_page"]["key_echo_is_password"] == "Password",
            f"echoMode={result['current_page']['key_echo_is_password']}",
        )

        # eye toggle
        self.on_gui(lambda: window.toggle_key_visibility())
        echo_on = self.on_gui(lambda: window.key_entry.echoMode().name)
        self.on_gui(lambda: window.toggle_key_visibility())
        echo_off = self.on_gui(lambda: window.key_entry.echoMode().name)
        result["eye_toggle"] = {"after_first": echo_on, "after_second": echo_off}
        check(
            "R7 当前配置页：显示/隐藏密钥可切换",
            echo_on == "Normal" and echo_off == "Password",
            json.dumps(result["eye_toggle"]),
        )

        # -- 新增配置（走真实的 clicked 信号） ------------------------------
        CREATED_DIALOGS.clear()
        stderr_buffer = io.StringIO()
        try:
            with redirect_stderr(stderr_buffer):
                self.on_gui(lambda: self._click_button_by_text("新增配置"))
        except BaseException as exc:  # noqa: BLE001
            result["click_error"] = repr(exc)
        created_editors = created("ProfileEditorDialog")
        result["new_profile_click"] = {
            "dialogs": created_editors,
            "stderr": stderr_buffer.getvalue()[:2000],
        }
        print("[new-profile-click] " + json.dumps(result["new_profile_click"], ensure_ascii=False))

        check(
            "R7 点击“新增配置”会打开编辑器",
            len(created_editors) >= 1,
            f"created={len(created_editors)} stderr={stderr_buffer.getvalue().strip()[:160]!r}",
        )
        if created_editors:
            first = created_editors[0]
            check(
                "R7 “新增配置”传入的是 record=None（不是 clicked 的 bool）",
                "error" not in first and first["arg_repr"][-1:] == ["None"],
                f"args={first['arg_repr']} error={first.get('error')}",
            )

        # -- 保存一个新配置（真实对话框代码，只是不进入模态循环） ----------
        CALLS.clear()
        editor = None

        def build_editor():
            return view.ProfileEditorDialog(window, None)

        editor = self.on_gui(build_editor)
        self.on_gui(lambda: editor.name_edit.setText("verify-profile-A"))
        self.on_gui(lambda: editor.api_key_edit.setText("sk-verify-A"))
        self.on_gui(lambda: editor.provider_edit.setText("VerifyProvider"))
        self.on_gui(lambda: editor.base_url_edit.setText("https://verify.example.com/v1"))
        self.on_gui(lambda: editor.model_combo.setCurrentText("gpt-5-verify"))

        closed: list[str] = []
        original_close = editor.close
        original_accept = editor.accept
        editor.close = lambda: (closed.append("close"), original_close())[1]  # type: ignore[method-assign]
        editor.accept = lambda: (closed.append("accept"), original_accept())[1]  # type: ignore[method-assign]

        self.on_gui(lambda: window.notify("__sentinel__"))  # keep the recorder honest
        CALLS.clear()
        saved_ok = True
        try:
            self.on_gui(lambda: editor._save())  # noqa: SLF001 - the button's real slot
        except BaseException as exc:  # noqa: BLE001
            saved_ok = False
            result["save_error"] = repr(exc)

        core.clear_profile_cache()
        records = self.on_gui(lambda: list(core.list_backup_records(window.current_path())))
        names = sorted(record.name for record in records)
        result["editor_save"] = {
            "ok": saved_ok,
            "closed": list(closed),
            "records": names,
            "notify": [item["args"] for item in calls_to("notify")],
            "show_info": [item["args"] for item in calls_to("show_info")],
            "load_path": [item["args"] for item in calls_to("load_path")],
            "error_label": self.on_gui(lambda: editor.error_label.text()),
            "table_rows": self.on_gui(lambda: window.profile_table.rowCount()),
            "row_records": self.on_gui(lambda: [record.name for record in window._row_records]),  # noqa: SLF001
        }
        print("[editor-save] " + json.dumps(result["editor_save"], ensure_ascii=False))

        check(
            "R7 编辑器保存：配置真的落盘",
            "verify-profile-A" in names,
            f"records={names} error_label={result['editor_save']['error_label']!r}",
        )
        check(
            "R7 编辑器保存：对话框关闭",
            bool(closed),
            f"closed={closed}",
        )
        check(
            "R7 编辑器保存：给出成功反馈",
            bool(calls_to("notify")),
            json.dumps(result["editor_save"]["notify"], ensure_ascii=False),
        )
        check(
            "R7 编辑器保存：列表已刷新",
            result["editor_save"]["table_rows"] == len(records)
            and len(result["editor_save"]["row_records"]) == len(records),
            f"rows={result['editor_save']['table_rows']} records={len(records)}",
        )

        # -- 编辑已有配置 --------------------------------------------------
        if records:
            target = records[0]

            def build_edit_dialog():
                return view.ProfileEditorDialog(window, target)

            edit_dialog = self.on_gui(build_edit_dialog)
            result["edit_dialog_prefill"] = self.on_gui(
                lambda: {
                    "title": edit_dialog.windowTitle(),
                    "name": edit_dialog.name_edit.text(),
                    "base_url": edit_dialog.base_url_edit.text(),
                    "provider": edit_dialog.provider_edit.text(),
                }
            )
            check(
                "R7 编辑配置：对话框回填了该配置的值",
                result["edit_dialog_prefill"]["name"] == target.name
                and result["edit_dialog_prefill"]["base_url"],
                json.dumps(result["edit_dialog_prefill"], ensure_ascii=False),
            )

            self.on_gui(
                lambda: edit_dialog.base_url_edit.setText("https://verify.example.com/v2")
            )
            self.on_gui(lambda: edit_dialog._save())  # noqa: SLF001
            core.clear_profile_cache()
            updated = self.on_gui(
                lambda: core.cached_profile_entry(target.path).base_url
            )
            result["edit_save_base_url"] = updated
            check(
                "R7 编辑配置：修改真的落盘",
                updated == "https://verify.example.com/v2",
                f"base_url={updated!r}",
            )
            self.on_gui(lambda: edit_dialog.close())

        # -- 搜索过滤 ------------------------------------------------------
        self.on_gui(lambda: window.show_page("profiles"))
        time.sleep(0.25)
        total_rows = self.on_gui(lambda: window.profile_table.rowCount())
        self.on_gui(lambda: window.profile_search_edit.setText("verify-profile-A"))
        time.sleep(0.25)
        filtered_rows = self.on_gui(lambda: window.profile_table.rowCount())
        self.on_gui(lambda: window.profile_search_edit.setText("__no_such_profile__"))
        time.sleep(0.25)
        empty_rows = self.on_gui(lambda: window.profile_table.rowCount())
        empty_text = self.on_gui(lambda: window.profile_empty_label.text())
        self.on_gui(lambda: window.profile_search_edit.setText(""))
        time.sleep(0.25)
        restored_rows = self.on_gui(lambda: window.profile_table.rowCount())
        result["search"] = {
            "total": total_rows,
            "filtered": filtered_rows,
            "empty": empty_rows,
            "empty_text": empty_text,
            "restored": restored_rows,
        }
        check(
            "R7 切换配置页：搜索过滤生效并可清空",
            total_rows >= 1
            and filtered_rows == 1
            and empty_rows == 0
            and restored_rows == total_rows,
            json.dumps(result["search"], ensure_ascii=False),
        )

        # -- 排序 ----------------------------------------------------------
        first_before = self.on_gui(lambda: window.profile_table.item(0, 0).text())
        self.on_gui(lambda: window._on_profile_header_clicked(0))  # noqa: SLF001
        time.sleep(0.2)
        header_text = self.on_gui(
            lambda: window.profile_table.horizontalHeaderItem(0).text()
        )
        first_after = self.on_gui(lambda: window.profile_table.item(0, 0).text())
        result["sort"] = {
            "first_before": first_before,
            "header": header_text,
            "first_after": first_after,
        }
        check(
            "R7 切换配置页：点表头可切换排序",
            "▼" in header_text,
            json.dumps(result["sort"], ensure_ascii=False),
        )

        # -- 切换到该配置（核心调用打桩，不真的启动 Codex） -----------------
        CALLS.clear()
        real_switch = core.switch_saved_profile
        switch_log: list[dict] = []

        def fake_switch(config_dir, backup_dir, allow_running_restart=False):
            switch_log.append(
                {
                    "config_dir": str(config_dir),
                    "backup_dir": str(backup_dir),
                    "allow_running_restart": allow_running_restart,
                }
            )
            core.apply_saved_profile(config_dir, backup_dir)
            return core.CodexLaunchResult(
                core.CodexRestartTarget(root_pid=0, executable=Path("codex.exe")), "start"
            )

        core.switch_saved_profile = fake_switch
        # The app asks for confirmation before it restarts Codex, and the modal
        # recorder answers every dialog with 0 - i.e. "no" - so without this stub
        # the switch aborts at the confirmation and nothing else runs.  Record the
        # question so the report shows the app really did ask.
        asked: list[str] = []
        window.ask_yes_no = lambda message, parent=None: (asked.append(message), True)[1]  # type: ignore[method-assign]
        try:
            self.on_gui(lambda: window.profile_table.selectRow(0))
            time.sleep(0.2)
            # Record the guard inputs: the method returns silently, so a bare
            # "nothing happened" would not say which condition was false.
            guards = self.on_gui(
                lambda: {
                    "selected": len(window._selected_profile_records()),  # noqa: SLF001
                    "multi_mode": window.profile_multi_mode,
                    "switch_in_progress": window.profile_switch_in_progress,
                    "rows": window.profile_table.rowCount(),
                    "selected_rows": sorted(
                        {index.row() for index in window.profile_table.selectedIndexes()}
                    ),
                }
            )
            self.on_gui(lambda: window._switch_selected_profile())  # noqa: SLF001
            deadline = time.time() + 12.0
            while time.time() < deadline:
                busy = self.on_gui(lambda: window.profile_switch_in_progress)
                if not busy:
                    break
                time.sleep(0.15)
            time.sleep(0.4)
        finally:
            core.switch_saved_profile = real_switch

        result["switch"] = {
            "guards": guards,
            "confirmation_asked": asked,
            "calls": switch_log,
            "notify": [item["args"] for item in calls_to("notify")],
            "busy_after": self.on_gui(lambda: window.profile_switch_in_progress),
        }
        print("[switch] " + json.dumps(result["switch"], ensure_ascii=False))
        switched = any(
            "已切换到配置" in str(args[0]) if args else False
            for args in result["switch"]["notify"]
        )
        check(
            "R7 切换配置：调用核心并给出反馈",
            bool(switch_log) and switched,
            json.dumps(result["switch"], ensure_ascii=False),
        )

        # -- 删除所选配置 --------------------------------------------------
        CALLS.clear()
        self.on_gui(lambda: window._set_profile_multi_mode(True))  # noqa: SLF001
        multi_visible = self.on_gui(lambda: window.profile_multi_bar.isVisible())
        self.on_gui(lambda: window.profile_table.selectAll())
        self.on_gui(lambda: window._update_profile_buttons())  # noqa: SLF001
        all_button_text = self.on_gui(lambda: window.profile_select_all_button.text())
        rows_before_delete = self.on_gui(lambda: window.profile_table.rowCount())

        window.ask_yes_no = lambda *a, **k: True  # type: ignore[method-assign]
        to_delete = self.on_gui(lambda: list(window._selected_profile_records()))  # noqa: SLF001
        self.on_gui(lambda: window._delete_profile_records(to_delete))  # noqa: SLF001
        time.sleep(0.4)
        core.clear_profile_cache()
        remaining = self.on_gui(lambda: list(core.list_backup_records(window.current_path())))
        result["delete"] = {
            "multi_bar_visible": multi_visible,
            "select_all_text": all_button_text,
            "rows_before": rows_before_delete,
            "deleted": [record.name for record in to_delete],
            "remaining": sorted(record.name for record in remaining),
            "notify": [item["args"] for item in calls_to("notify")],
        }
        print("[delete] " + json.dumps(result["delete"], ensure_ascii=False))
        check(
            "R7 删除所选配置：多选栏出现且可全选",
            multi_visible and all_button_text == "取消全选",
            json.dumps(result["delete"], ensure_ascii=False),
        )
        check(
            "R7 删除所选配置：配置真的被删除",
            not remaining,
            f"remaining={result['delete']['remaining']}",
        )
        self.on_gui(lambda: window._set_profile_multi_mode(False))  # noqa: SLF001

        # -- 官方登录页 ----------------------------------------------------
        self.on_gui(lambda: window.show_page("official"))
        time.sleep(0.25)
        official_before = self.on_gui(
            lambda: (
                window.official_status_label.text(),
                window.official_action_button.text(),
                window.official_action_button.isEnabled(),
            )
        )
        window.ask_yes_no = lambda *a, **k: True  # type: ignore[method-assign]
        self.on_gui(lambda: window.official_action_button.click())
        time.sleep(0.5)
        official_after = self.on_gui(
            lambda: (
                window.official_status_label.text(),
                window.official_action_button.text(),
                window.official_action_button.isEnabled(),
            )
        )
        mode_on = core.is_official_login_mode(window.current_path())
        result["official"] = {
            "before": list(official_before),
            "after": list(official_after),
            "is_official_login_mode": mode_on,
        }
        print("[official] " + json.dumps(result["official"], ensure_ascii=False))
        check(
            "R7 官方登录页：按钮切换到官方模式并刷新状态",
            mode_on
            and official_after[0] != official_before[0]
            and not official_after[2],
            json.dumps(result["official"], ensure_ascii=False),
        )

        # -- 更新检查 ------------------------------------------------------
        self.on_gui(lambda: window.show_page("current"))
        window._set_available_update(None)  # noqa: SLF001
        real_fetch = core.fetch_latest_release
        core.fetch_latest_release = lambda timeout=None: core.UpdateInfo(
            version="v99.0.0", page_url="https://example.invalid/release"
        )
        try:
            self.on_gui(lambda: window.start_update_check(manual=False))
            deadline = time.time() + 12.0
            while time.time() < deadline:
                busy = self.on_gui(lambda: window._update_check_in_progress)  # noqa: SLF001
                if not busy:
                    break
                time.sleep(0.15)
            time.sleep(0.3)
        finally:
            core.fetch_latest_release = real_fetch

        update = self.on_gui(lambda: window.available_update)
        result["update_check"] = {
            "version": getattr(update, "version", None),
            "dot_visible": self.on_gui(lambda: window.about_button._dot),  # noqa: SLF001
            "busy": self.on_gui(lambda: window._update_check_in_progress),  # noqa: SLF001
        }
        print("[update-check] " + json.dumps(result["update_check"], ensure_ascii=False))
        check(
            "R7 检查更新：拿到新版本并点亮标题栏小红点",
            result["update_check"]["version"] == "v99.0.0"
            and result["update_check"]["dot_visible"] is True,
            json.dumps(result["update_check"], ensure_ascii=False),
        )

        # -- 其余页面的导航 ------------------------------------------------
        nav = {}
        for key in ("current", "profiles", "official", "guide", "recommended"):
            self.on_gui(lambda target=key: window.show_page(target))
            time.sleep(0.15)
            nav[key] = self.on_gui(
                lambda target=key: {
                    "active": window.active_page,
                    "stacked": window.page_host.currentWidget() is window.pages[target],
                    "checked": window.nav_items[target].isChecked(),
                    "visible": window.pages[target].isVisible(),
                }
            )
        result["nav"] = nav
        check(
            "R7 五个页面都能切换且高亮正确",
            all(
                item["active"] == key and item["stacked"] and item["checked"] and item["visible"]
                for key, item in nav.items()
            ),
            json.dumps(nav, ensure_ascii=False),
        )

        # -- 对话框可构造 --------------------------------------------------
        CREATED_DIALOGS.clear()
        self.on_gui(lambda: window.show_about_dialog())
        self.on_gui(lambda: window.show_donation_dialog())
        # show_onboarding_dialog is stubbed out at class level for this run, so
        # construct the dialog itself rather than going through that stub.
        self.on_gui(lambda: view.OnboardingDialog(window).run())
        self.on_gui(lambda: window.ask_config_name(CONFIG_DIR, "验证名称", "验证用途"))
        self.on_gui(lambda: view.ScanPickerDialog(window, [CONFIG_DIR]).run())
        self.on_gui(lambda: view.MessageDialog(window, "验证消息", kind="info").run())
        self.on_gui(lambda: view.MessageDialog(window, "验证提问", kind="question").run())
        made = [item["dialog"] for item in CREATED_DIALOGS]
        failed = [item for item in CREATED_DIALOGS if "error" in item]
        result["dialogs"] = {"created": made, "failed": failed}
        print("[dialogs] " + json.dumps(result["dialogs"], ensure_ascii=False))
        check(
            "R7 关于/赞赏/引导/命名/扫描/消息对话框都能打开",
            not failed
            and {
                "AboutDialog",
                "DonationDialog",
                "OnboardingDialog",
                "ConfigNameDialog",
                "ScanPickerDialog",
                "MessageDialog",
            }
            <= set(made),
            json.dumps(result["dialogs"], ensure_ascii=False),
        )

        FUNCTIONAL["result"] = result

    def _click_button_by_text(self, text: str) -> bool:
        from PySide6.QtWidgets import QPushButton

        for button in self.window.findChildren(QPushButton):
            if button.text() == text and button.isVisible():
                button.click()
                return True
        return False

    def stage_final_size(self) -> None:
        hwnd = self.hwnd
        client = W.client_rect(hwnd)
        frame = W.frame_thickness(hwnd)
        style = W.get_style(hwnd)
        check(
            "R6 全部流程结束后窗口仍是 820x500、无原生边框",
            list(client) == [core.WINDOW_WIDTH, core.WINDOW_HEIGHT]
            and tuple(frame) == (0, 0)
            and not (style & W.WS_CAPTION),
            f"client={list(client)} frame={list(frame)} style={style:#010x}",
        )
        FUNCTIONAL["final"] = {
            "client": list(client),
            "frame": list(frame),
            "style": hex(style),
            "exstyle": hex(W.get_ex_style(hwnd)),
            "iconic": W.is_iconic(hwnd),
        }

    # -- run ---------------------------------------------------------------

    def run(self) -> None:
        self.hwnd = self.on_gui(self.window._window_handle)  # noqa: SLF001
        if not self.hwnd:
            check("拿到窗口句柄", False, "winId() returned 0")
            return
        FUNCTIONAL["hwnd"] = hex(self.hwnd)
        FUNCTIONAL["describe"] = W.describe(self.hwnd)

        # The taskbar registration is deferred by QTimer, so give it its chance.
        time.sleep(0.6)

        # One pre-flight for the whole run.  Everything that injects a mouse
        # event depends on this, and when it is unavailable the results are not
        # merely missing - they are actively misleading, because the events go to
        # whatever window is in front instead.
        injectable, detail = wait_for_input_injection(45)
        self.input_ok = injectable
        self.input_detail = detail
        FUNCTIONAL["input_injection"] = {"available": injectable, "detail": detail}
        check(
            "合成鼠标输入可用（拖动与任务栏点击的前提）",
            injectable,
            detail,
            environment=(not injectable),
        )

        stages = (
            ("frame", self.stage_frame),
            ("drag", self.stage_drag),
            ("maximize", self.stage_maximize),
            ("taskbar", self.stage_taskbar),
            ("cycles", self.stage_cycles),
            ("functional", self.stage_functional),
            ("final", self.stage_final_size),
        )
        for name, stage in stages:
            try:
                stage()
            except InputUnavailable as exc:
                self.environment_errors.append(f"{name}: {exc}")
                check(
                    f"阶段 {name} 完整跑完",
                    False,
                    f"合成输入被桌面拒绝，该阶段无法评估：{exc}",
                    environment=True,
                )
            except BaseException as exc:  # noqa: BLE001
                self.errors.append(f"{name}: {type(exc).__name__}: {exc}")
                check(f"阶段 {name} 完整跑完", False, f"{type(exc).__name__}: {exc}")


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    seed_config_dir()
    install_modal_recorders()

    # Keep the run hermetic: no onboarding, no network update check, and no
    # discovery of the user's real ~/.codex.
    view.CodexConfigWindow.show_onboarding_dialog = lambda self, force=False: None
    view.CodexConfigWindow.check_for_updates_on_startup = lambda self: None
    view.CodexConfigWindow._load_initial_path = lambda self: None

    # Record the GUI-side calls we want to assert on, without changing behaviour.
    real_notify = view.CodexConfigWindow.notify
    real_show_info = view.CodexConfigWindow.show_info
    real_load_path = view.CodexConfigWindow.load_path
    view.CodexConfigWindow.notify = lambda self, message, duration=1800: (
        record_call("notify")(message),
        real_notify(self, message, duration),
    )[1]
    view.CodexConfigWindow.show_info = lambda self, message, parent=None: (
        record_call("show_info")(message),
        real_show_info(self, message, parent),
    )[1]
    view.CodexConfigWindow.load_path = lambda self, path: (
        record_call("load_path")(str(path)),
        real_load_path(self, path),
    )[1]

    app = view.create_application()
    window = view.CodexConfigWindow()
    window.show()
    window.load_path(CONFIG_DIR)
    window.raise_()
    window.activateWindow()

    driver = Driver(app, window)
    QTimer.singleShot(900, lambda: threading.Thread(target=driver.run, daemon=True).start())
    QTimer.singleShot(300_000, app.quit)

    app.exec()

    failures = [item for item in CHECKS if not item["ok"] and not item["environment"]]
    skipped = [item for item in CHECKS if item["environment"]]
    report = {
        "sandbox": str(SANDBOX),
        "config_dir": str(CONFIG_DIR),
        "window": [core.WINDOW_WIDTH, core.WINDOW_HEIGHT],
        "checks": CHECKS,
        "failures": failures,
        "environment_skipped": skipped,
        "driver_errors": driver.errors,
        "environment_errors": driver.environment_errors,
        "drags": DRAGS,
        "cycles": CYCLES_LOG,
        "functional": FUNCTIONAL,
        "created_dialogs": CREATED_DIALOGS,
        "artifacts": ARTIFACTS,
    }
    path = os.path.join(OUT_DIR, "verify-qt-report.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(f"REPORT {path}")
    print(
        "SUMMARY "
        + json.dumps(
            {
                "passed": len(CHECKS) - len(failures) - len(skipped),
                "failed": len(failures),
                "environment_skipped": len(skipped),
                "failures": [item["name"] for item in failures],
                "skipped": [item["name"] for item in skipped],
                "driver_errors": driver.errors,
                "environment_errors": driver.environment_errors,
            },
            ensure_ascii=False,
        )
    )
    sandbox_env.cleanup(SANDBOX)
    return 1 if failures or driver.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
