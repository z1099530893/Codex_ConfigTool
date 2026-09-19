"""Objective drag-integrity test: does the window repaint while being dragged?

Requirement 2 asks that dragging the custom title bar must not fragment, tear,
resize or otherwise break the window.  Position checks at the start and end of a
drag cannot see a repaint failure - the window can arrive at the right place
while parts of it still show stale or foreign pixels.

This captures the window straight off the screen (GDI ``BitBlt``, not
``PrintWindow``, so it is the real composited result) while a synthetic drag is
in progress, and compares the window body against a stationary reference.  The
content does not change during a move, so a correct repaint means the body is
pixel-identical; any leftover shows up as a diff fraction.

Two sampling modes:

* **paused** - the cursor stops for a moment at a waypoint, so the capture is
  aligned and the comparison can be strict.  Catches "arrived but did not
  repaint".
* **in-flight** - captured while the mouse is still moving, compared with a
  small alignment search.  Catches gross tearing.

Also checks geometry at every sample and looks for a ghost left at the original
position after the drag.

Usage:
    python verify_app_drag_integrity.py [--exe path]
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
from PIL import Image, ImageChops  # noqa: E402

from accept_packaged_exe import (  # noqa: E402
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    InputUnavailable,
    all_visible_windows,
    cursor_pos,
    find_main_window,
    move_cursor,
    wait_for_input_injection,
)

TITLE_BAR_HEIGHT = 38
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
OUT_DIR = os.path.join(HERE, "out")
DIFF_THRESHOLD = 25
# A correct repaint is pixel-identical apart from the cursor and the button
# hover state, both of which live in the title bar we exclude.
BODY_DIFF_TOLERANCE = 0.02
# For the ghost check we need a region whose appearance is distinctive, or the
# desktop behind the vacated area can coincidentally match.  The dark sidebar
# (white text on #5b5b5b) is ideal; the light body is not - measuring the whole
# body gives only 0.41 separation, the sidebar interior gives 0.92.
GHOST_REGION = (10, 150, 132, 400)
# Above this share of the distinctive region still matching the app means a
# stale fragment was left painted on screen.
GHOST_MATCH_TOLERANCE = 0.5

user32 = ctypes.windll.user32


def body(image: Image.Image) -> Image.Image:
    """The part of a window capture below the custom title bar."""
    return image.crop((0, TITLE_BAR_HEIGHT, image.width, image.height))


def diff_fraction(a: Image.Image, b: Image.Image) -> float:
    if a.size != b.size:
        return 1.0
    hist = ImageChops.difference(a, b).convert("L").histogram()
    total = sum(hist)
    return sum(hist[DIFF_THRESHOLD:]) / total if total else 1.0


def best_match(shot: Image.Image, reference: Image.Image, max_shift: int = 4):
    """Smallest diff fraction over small alignment offsets (for moving captures)."""
    best, best_shift = 1.0, (0, 0)
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            width = min(shot.width, reference.width) - abs(dx)
            height = min(shot.height, reference.height) - abs(dy)
            if width <= 0 or height <= 0:
                continue
            a = shot.crop((max(dx, 0), max(dy, 0), max(dx, 0) + width, max(dy, 0) + height))
            b = reference.crop(
                (max(-dx, 0), max(-dy, 0), max(-dx, 0) + width, max(-dy, 0) + height)
            )
            fraction = diff_fraction(a, b)
            if fraction < best:
                best, best_shift = fraction, (dx, dy)
    return best, best_shift


def sample(hwnd: int, reference_body: Image.Image, label: str, tolerance_shift: int = 0):
    """Capture the window now and compare its body with the reference."""
    left, top, width, height = W.window_rect(hwnd)
    client = W.client_rect(hwnd)
    frame = W.frame_thickness(hwnd)
    shot = grab.grab_window(hwnd, margin=0)
    shot_body = body(shot)
    if tolerance_shift:
        fraction, shift = best_match(shot_body, reference_body, tolerance_shift)
    else:
        fraction, shift = diff_fraction(shot_body, reference_body), (0, 0)
    record = {
        "label": label,
        "rect": [left, top, width, height],
        "client": list(client),
        "frame": list(frame),
        "size_ok": list(client) == [WINDOW_WIDTH, WINDOW_HEIGHT],
        "frame_ok": frame == (0, 0),
        "body_diff": round(fraction, 5),
        "best_shift": list(shift),
        "repaint_ok": fraction <= BODY_DIFF_TOLERANCE,
    }
    print("[sample] " + json.dumps(record, ensure_ascii=False), flush=True)
    return record, shot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=os.path.join(ROOT, "dist", "CodexConfigTool.exe"))
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

    records: list[dict] = []
    failures: list[str] = []
    saved_cursor = cursor_pos()

    try:
        # Reference: stationary, settled.
        W.ensure_clickable(hwnd, W.window_rect(hwnd)[0] + 300, W.window_rect(hwnd)[1] + 19)
        time.sleep(0.6)
        reference_shot = grab.grab_window(hwnd, margin=0)
        reference_shot.save(os.path.join(OUT_DIR, "drag-ref.png"))
        reference_body = body(reference_shot)
        start_left, start_top, _, _ = W.window_rect(hwnd)
        print(f"reference captured, rect=({start_left},{start_top})")

        press_x = start_left + 300
        press_y = start_top + TITLE_BAR_HEIGHT // 2
        move_cursor(press_x, press_y)
        time.sleep(0.2)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
        time.sleep(0.15)

        total_dx, total_dy = 140, 80
        steps = 28
        paused_at = {7: "paused-1", 16: "paused-2", 24: "paused-3"}
        in_flight_at = {11: "inflight-1", 20: "inflight-2"}

        for step in range(1, steps + 1):
            x = press_x + total_dx * step // steps
            y = press_y + total_dy * step // steps
            move_cursor(x, y)
            time.sleep(0.02)

            if step in in_flight_at:
                # Keep the button down and capture while still moving.
                record, _ = sample(hwnd, reference_body, in_flight_at[step], tolerance_shift=4)
                records.append(record)
            if step in paused_at:
                time.sleep(0.35)  # let it settle, then compare strictly
                record, shot = sample(hwnd, reference_body, paused_at[step])
                records.append(record)
                if step == 16:
                    shot.save(os.path.join(OUT_DIR, "drag-mid.png"))
                    grab.grab_primary_screen().save(os.path.join(OUT_DIR, "drag-mid-screen.png"))

        time.sleep(0.3)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
        time.sleep(0.8)
        move_cursor(saved_cursor[0], saved_cursor[1])
        time.sleep(0.3)

        final_rect = W.window_rect(hwnd)
        print(f"after drag rect={final_rect}")

        # Ghost check: the vacated area must no longer show the app's content.
        # Measured on the distinctive dark sidebar; a stale fragment would keep
        # it matching, a clean repaint leaves the desktop showing through.
        old_area = grab.grab_rect(start_left, start_top, WINDOW_WIDTH, WINDOW_HEIGHT)
        old_area.save(os.path.join(OUT_DIR, "drag-old-area.png"))
        ghost_match = 1.0 - diff_fraction(
            old_area.crop(GHOST_REGION), reference_shot.crop(GHOST_REGION)
        )
        print(f"ghost check: {ghost_match:.4f} of the vacated sidebar still matches the app")
        print("  (near 0 = clean repaint, near 1 = a stale fragment was left behind)")

        # Geometry at rest.
        client = W.client_rect(hwnd)
        frame = W.frame_thickness(hwnd)
        records.append(
            {
                "label": "final",
                "rect": list(final_rect),
                "client": list(client),
                "frame": list(frame),
                "size_ok": list(client) == [WINDOW_WIDTH, WINDOW_HEIGHT],
                "frame_ok": frame == (0, 0),
            }
        )
        if list(client) != [WINDOW_WIDTH, WINDOW_HEIGHT]:
            failures.append(f"final: client {client}")
        if frame != (0, 0):
            failures.append(f"final: native frame {frame}")
        moved = [final_rect[0] - start_left, final_rect[1] - start_top]
        if moved != [total_dx, total_dy]:
            failures.append(f"final: moved {moved} instead of {[total_dx, total_dy]}")

        for record in records:
            if not record.get("size_ok", True):
                failures.append(f"{record['label']}: client {record['client']} during drag")
            if not record.get("frame_ok", True):
                failures.append(f"{record['label']}: native frame {record['frame']} during drag")
            if record.get("repaint_ok") is False:
                failures.append(
                    f"{record['label']}: body diff {record['body_diff']}"
                    f" (shift {record['best_shift']})"
                )
        if ghost_match > GHOST_MATCH_TOLERANCE:
            failures.append(f"ghost left at the original position (match {ghost_match:.3f})")

        report = {
            "exe": args.exe,
            "hwnd": hex(hwnd),
            "start_rect": [start_left, start_top, WINDOW_WIDTH, WINDOW_HEIGHT],
            "final_rect": list(final_rect),
            "moved": moved,
            "requested": [total_dx, total_dy],
            "ghost_region": list(GHOST_REGION),
            "ghost_match": round(ghost_match, 5),
            "samples": records,
            "failures": failures,
        }
        path = os.path.join(OUT_DIR, "drag-integrity-report.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print("REPORT " + path)
        print(
            "SUMMARY "
            + json.dumps(
                {
                    "verdict": "PASS" if not failures else "FAIL",
                    "samples": len(records),
                    "max_body_diff": max(
                        (r.get("body_diff", 0.0) for r in records), default=0.0
                    ),
                    "failures": failures,
                },
                ensure_ascii=False,
            )
        )
        return 0 if not failures else 1
    except InputUnavailable as error:
        print(f"ENVIRONMENT input injection lost mid-run: {error}")
        return 3
    finally:
        try:
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
        except Exception:  # noqa: BLE001
            pass
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
