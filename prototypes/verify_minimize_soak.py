"""Soak test: does the app survive being minimized for a while?

The handoff records a historical regression where "Win32 ``ShowWindow`` attempts
caused the main-window minimize button to do nothing or caused the application to
exit after a delay".  The acceptance test only checks that the process is alive
about 1.5 s after minimize, which would not notice a delayed exit.  This holds
the window minimized for a minute, then restored for half a minute, polling
throughout.

It also watches the HWND: if Tk re-created the window, ``IsWindow`` would fail or
the handle would change, which is the signature of the original bug.

Usage:
    python verify_minimize_soak.py [--minimized 60] [--restored 30]
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

from accept_packaged_exe import (  # noqa: E402
    TASKBAR_SCAN,
    InputUnavailable,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    all_visible_windows,
    app_button,
    bbox_of,
    changed_runs,
    click_app,
    click_taskbar_bbox,
    describe_runs,
    ensure_foreground,
    find_main_window,
    process_alive,
    wait_for_input_injection,
)

OUT_DIR = os.path.join(HERE, "out")
TITLE_BAR_HEIGHT = 38
MINIMIZE_BUTTON_OFFSET = 63


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=os.path.join(ROOT, "dist", "CodexConfigTool.exe"))
    parser.add_argument("--minimized", type=float, default=60.0)
    parser.add_argument("--restored", type=float, default=30.0)
    parser.add_argument("--wait-input", type=float, default=120.0)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    injectable, detail = wait_for_input_injection(args.wait_input)
    if not injectable:
        print("ENVIRONMENT input injection unavailable: " + detail)
        return 3

    pre = set(all_visible_windows())
    process = subprocess.Popen([args.exe], cwd=ROOT)
    hwnd, pid = find_main_window(pre)
    if not hwnd:
        print("main window not found")
        return 2
    time.sleep(2.5)
    print(f"window {hwnd:#x} pid={pid} {W.describe(hwnd)}")

    notes: list[str] = []
    samples: list[dict] = []
    failures: list[str] = []
    limitations: list[str] = []

    def watch(phase: str, seconds: float, expect_iconic: bool) -> None:
        """Poll the window for ``seconds`` and record every deviation."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            alive = process_alive(pid)
            window_exists = bool(W.user32.IsWindow(wintypes.HWND(hwnd)))
            iconic = W.is_iconic(hwnd) if window_exists else None
            client = list(W.client_rect(hwnd)) if window_exists and not iconic else None
            frame = list(W.frame_thickness(hwnd)) if window_exists and not iconic else None
            record = {
                "phase": phase,
                "t": round(seconds - (deadline - time.time()), 1),
                "alive": alive,
                "window_exists": window_exists,
                "iconic": iconic,
                "client": client,
                "frame": frame,
            }
            samples.append(record)
            if not alive:
                failures.append(f"{phase}: process died at t={record['t']}s")
                print("[soak] " + json.dumps(record, ensure_ascii=False))
                return
            if not window_exists:
                failures.append(f"{phase}: window handle {hwnd:#x} vanished at t={record['t']}s")
                print("[soak] " + json.dumps(record, ensure_ascii=False))
                return
            if expect_iconic and not iconic:
                failures.append(f"{phase}: window stopped being iconic at t={record['t']}s")
            if not expect_iconic and iconic:
                failures.append(f"{phase}: window re-minimized at t={record['t']}s")
            if client is not None and client != [WINDOW_WIDTH, WINDOW_HEIGHT]:
                failures.append(f"{phase}: client {client} at t={record['t']}s")
            if frame is not None and frame != [0, 0]:
                failures.append(f"{phase}: native frame {frame} at t={record['t']}s")
            time.sleep(2.0)

    try:
        normal_strip = os.path.join(OUT_DIR, "soak-normal-taskbar.png")
        # The baseline must be taken while the app owns the foreground, because
        # that is the only time its taskbar button carries the "active"
        # highlight the diff below relies on.
        ensure_foreground(hwnd, notes, "soak baseline")
        grab.grab_taskbar_strip().save(normal_strip)

        before = W.window_rect(hwnd)
        if not click_app(
            hwnd,
            before[0] + before[2] - MINIMIZE_BUTTON_OFFSET,
            before[1] + TITLE_BAR_HEIGHT // 2,
            "soak minimize",
            notes,
        ):
            failures.append("minimize button not clickable")
        time.sleep(1.5)
        if not W.is_iconic(hwnd):
            failures.append("window did not minimize")
            print("window did not minimize; aborting soak")
            return report(args, hwnd, pid, samples, notes, failures, limitations)
        print(f"minimized; watching for {args.minimized:.0f}s")

        # locate the taskbar button now, while minimized
        minimized_strip = os.path.join(OUT_DIR, "soak-minimized-taskbar.png")
        grab.grab_taskbar_strip().save(minimized_strip)
        runs = changed_runs(minimized_strip, normal_strip, TASKBAR_SCAN)
        button, deltas = app_button(runs, normal_strip, minimized_strip)
        print(f"state runs: {describe_runs(runs)}  deltas {deltas}")
        if not button:
            limitations.append(
                "taskbar button not locatable in the normal/minimized diff "
                f"(runs: {describe_runs(runs)})"
            )
            print("WARNING " + limitations[-1])

        watch("minimized", args.minimized, expect_iconic=True)
        if failures:
            return report(args, hwnd, pid, samples, notes, failures, limitations)

        # restore through the real taskbar button when we managed to find it
        restored = False
        restore_via = None
        if button:
            bbox = bbox_of(button)
            W.pin_on_top(hwnd, False)
            click_taskbar_bbox(bbox, notes, "soak restore")
            time.sleep(1.5)
            if not W.is_iconic(hwnd):
                restored = True
                restore_via = "taskbar-click"
        if not restored:
            # Degrade rather than accuse: not finding the button is a harness
            # limitation, not evidence that the app cannot be restored.  The
            # acceptance test already covers the taskbar-click path.
            limitations.append(
                "restore used the Win32 API fallback"
                + (" (button not locatable)" if not button else " (taskbar click had no effect)")
            )
            W.restore_window(hwnd)
            time.sleep(1.0)
            if not W.is_iconic(hwnd):
                restored = True
                restore_via = "api-fallback"
        if not restored:
            failures.append("window could not be restored at all")
            print("window could not be restored; aborting soak")
            return report(args, hwnd, pid, samples, notes, failures, limitations)
        print(f"restored via {restore_via}; watching for {args.restored:.0f}s")
        watch("restored", args.restored, expect_iconic=False)

        return report(args, hwnd, pid, samples, notes, failures, limitations)
    except InputUnavailable as error:
        print(f"ENVIRONMENT input injection lost mid-run: {error}")
        return 3
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)


def report(args, hwnd, pid, samples, notes, failures, limitations) -> int:
    path = os.path.join(OUT_DIR, "minimize-soak-report.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "exe": args.exe,
                "hwnd": hex(hwnd),
                "pid": pid,
                "minimized_seconds": args.minimized,
                "restored_seconds": args.restored,
                "samples": samples,
                "interaction_notes": notes,
                "failures": failures,
                "limitations": limitations,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
    alive = [s for s in samples if s["alive"]]
    print("REPORT " + path)
    print(
        "SUMMARY "
        + json.dumps(
            {
                "verdict": "PASS" if not failures else "FAIL",
                "samples": len(samples),
                "alive_samples": len(alive),
                "failures": failures,
                "limitations": limitations,
            },
            ensure_ascii=False,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
