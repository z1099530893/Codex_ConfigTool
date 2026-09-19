"""Measure the flash when the window is restored from the taskbar.

Reported symptom: the whole main UI "flashes once" on restore.  A flash is a frame
that is not the final content - a blank window, a partly painted one, or the
toplevel background before its children have drawn.  That is measurable: capture
the window as fast as possible while it is being restored and compare every frame
against the settled result.

Captures use GDI ``BitBlt`` off the real screen, so a frame that was only briefly
on screen is still caught; ``PrintWindow`` would re-render the window and hide
exactly the artefact being hunted.

Every frame is scored three ways, all computed from PIL histograms so the scoring
costs about a millisecond and cannot itself slow the sampling down:

* ``body_diff`` - fraction of body pixels differing from the settled reference,
* ``bg_fraction`` - fraction of body pixels equal to the toplevel background
  colour, i.e. how much of the window is *not* drawn content,
* ``mean`` - mean luminance, to catch an all-black or all-white frame.

A clean restore has ``body_diff`` near 0 in every frame.  A flash shows up as
frames with a large ``body_diff``; the worst one is saved to
``out/restore-flash-worst-runN.png`` next to the reference for inspection.

Usage:
    python verify_restore_flash.py [--exe path] [--runs 3]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import grab  # noqa: E402
import winapi as W  # noqa: E402
from PIL import Image, ImageChops, ImageStat  # noqa: E402

from accept_packaged_exe import (  # noqa: E402
    MINIMIZE_BUTTON_OFFSET,
    TITLE_BAR_HEIGHT,
    TASKBAR_SCAN,
    InputUnavailable,
    all_visible_windows,
    app_button,
    bbox_of,
    changed_runs,
    click_app,
    click_taskbar_bbox,
    close_existing_app_windows,
    close_existing_instances,
    ensure_foreground,
    find_main_window,
    process_alive,
    wait_for_input_injection,
)

OUT_DIR = os.path.join(HERE, "out")
DIFF_THRESHOLD = 24
# The toplevel background; a frame made mostly of this is an undrawn window.
WINDOW_BG = (243, 244, 247)
BG_TOLERANCE = 12
# A frame differing from the settled result by more than this fraction of its body
# is a visible artefact, not antialiasing noise.
FLASH_FRACTION = 0.02
# This UI's surfaces sit very close together, and that breaks any coarse
# threshold.  Measured on the saved reference:
#
#   (243,244,247)  toplevel background      - the colour the flash paints
#   (247,248,249)  a second light surface   -  4 units away
#   (255,255,255)  the white card fill      - 12 units away
#   (32,36,43)     body text                - 211 units away
#
# ``BG_TOLERANCE=12`` therefore counts the entire white card as "background", and
# ``DIFF_THRESHOLD=24`` is applied to *luminance*, so a card blanking to the
# toplevel background moves luminance by only ~11 and is not counted as a change
# either.  Both existing metrics are structurally blind in the content area - not
# merely insensitive - which is why forcing the probe there scored 0/6 while the
# sidebar scored 5/6.  The content metric below uses a tolerance inside the 4..12
# gap so the card counts as content, and normalises by the content pixel count so
# a sparse region has the same power as a dense one.
CONTENT_TOLERANCE = 4
# Fraction of the reference's visible content that a frame wiped out.
CONTENT_ERASE_FRACTION = 0.30
# "Is this frame an unpainted surface?" has to be asked relative to the probe's own
# settled brightness, not against a constant.  The old check used ``mean < 200``,
# which is a perfectly good threshold for a light region and a meaningless one for
# the auto-chosen probe: the dark sidebar patch settles at ``mean 126.26``, so a
# *partial blank* at ``mean 168.5`` is 42 units **lighter** than the settled UI and
# was nevertheless counted as "darker than the UI".  That inflated the cost of
# ``WS_EX_COMPOSITED`` - the one variant worth considering - by attributing it a
# black-frame failure mode it does not have.  A frame is unpainted when it is
# below the settled patch by more than this margin.
DARK_MARGIN = 20
# Sampling the whole window costs ~20 ms per frame, which is longer than the
# flash itself and makes detection a coin toss.  ``--probe patch`` samples one
# small region instead: the region is chosen from the reference as the one that is
# normally *least* background-coloured, so a blank-out is unmistakable there, and
# the cheap capture raises the frame rate enough to catch it every time.
PATCH_FRACTION = 0.30
PATCH_SIZE = (180, 120)
PATCH_STEP = 40
# How long to sit with no restores while sampling the app's idle CPU.  Long enough
# to average out the settle after startup, short enough not to dominate a run.
IDLE_CPU_SECONDS = 3.0
IDLE_CPU_WINDOWS = 3


def body(image: Image.Image) -> Image.Image:
    """Everything below the custom title bar (cursor and hover states live there)."""
    return image.crop((0, TITLE_BAR_HEIGHT, image.width, image.height))


def diff_fraction(a: Image.Image, b: Image.Image) -> float:
    """Fraction of pixels differing by more than ``DIFF_THRESHOLD``.

    Histogram-based, so the whole comparison is one C-level pass.
    """
    if a.size != b.size:
        return 1.0
    box = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    counts = box.histogram()
    total = a.size[0] * a.size[1]
    return sum(counts[DIFF_THRESHOLD + 1:]) / total if total else 0.0


def bg_fraction(image: Image.Image) -> float:
    """Fraction of pixels equal to the undrawn toplevel background colour."""
    grey = image.convert("L")
    counts = grey.histogram()
    total = grey.size[0] * grey.size[1]
    if not total:
        return 0.0
    level = sum(WINDOW_BG) // 3
    low, high = max(0, level - BG_TOLERANCE), min(255, level + BG_TOLERANCE)
    return sum(counts[low:high + 1]) / total


def content_mask(image: Image.Image, tolerance: int | None = None) -> Image.Image:
    """Mask of pixels that are *not* the undrawn toplevel background.

    Uses the per-channel maximum distance, not luminance.  Luminance is a
    weighted sum, so a strongly tinted pixel is under-reported: the flash fill
    (243,244,247) against the white card (255,255,255) differs by 12 in red but
    only ~11 in luminance, and against a saturated colour the gap is far larger
    still.  The per-channel maximum is the honest distance.

    ``tolerance`` defaults to the module constant *at call time* rather than being
    bound as a default argument, so ``--content-tolerance`` can retune every call
    site at once instead of only the ones that remember to pass it.
    """
    if tolerance is None:
        tolerance = CONTENT_TOLERANCE
    solid = Image.new("RGB", image.size, WINDOW_BG)
    red, green, blue = ImageChops.difference(image.convert("RGB"), solid).split()
    strongest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return strongest.point(lambda value: 255 if value > tolerance else 0, "L")


def content_erase_fraction(
    image: Image.Image,
    reference: Image.Image,
    tolerance: int | None = None,
) -> float | None:
    """Fraction of the reference's visible content that this frame wiped out.

    ``diff_fraction`` counts every changed pixel and normalises by the region
    size, so in a sparse region a *complete* blank-out scores as low as the
    region's content density.  The content patch of this app is 48% content at
    tolerance 4 but only 17% at the coarse tolerance, so the old metric could
    score a full blank-out at 0.17 and miss it under a 0.30 threshold.

    This metric normalises by the content pixel count instead, which makes the
    score a property of the *event* rather than of the region: a blank-out reads
    ~1.0 whether the region is the sidebar (84% content) or the content area
    (48%).  That is what makes the two regions directly comparable, and it is
    why the settled frame scores ~0 regardless of tolerance - the frame is
    compared against the reference's own content mask, so an unchanged pixel can
    never be counted as erased.
    """
    if image.size != reference.size:
        return None
    reference_content = content_mask(reference, tolerance)
    total = reference_content.histogram()[255]
    if not total:
        return None
    frame_is_background = content_mask(image, tolerance).point(lambda value: 255 - value)
    erased = ImageChops.multiply(reference_content, frame_is_background).histogram()[255]
    return round(erased / total, 4)


def exact_bg_fraction(image: Image.Image) -> float:
    """Fraction of pixels *exactly* equal to the toplevel background.

    This is the mechanism discriminator, and brightness cannot replace it.  A frame
    filled with Tk's own background and a frame showing whatever window is *behind*
    the app are both light and both read ``mean ~244`` - but only the first is made
    of this exact colour, because Tk paints its background exactly.  Measured on one
    run: toplevel fill reads 100%, a transparent window reads 0%, and a settled frame
    reads whatever the UI happens to contain (15.6% sidebar, 37.4% content here).

    Getting this wrong is not hypothetical - the largest artefact in the output folder
    was a transparent-window frame, and quoting it mis-attributed the cause and
    understated the effect.
    """
    width, height = image.size
    total = width * height
    if not total:
        return 0.0
    rgb = image.convert("RGB")
    counts = rgb.getcolors(maxcolors=total)
    if counts is None:
        return 0.0
    exact = sum(count for count, colour in counts if tuple(colour) == WINDOW_BG)
    return round(exact / total, 4)


def score(image: Image.Image, reference: Image.Image, crop_body: bool = True) -> dict:
    """Compare a capture against the settled reference.

    ``crop_body`` is False when the image is already a probe patch, which must be
    compared as-is: cropping the title-bar height off a 120 px patch would leave a
    different size from the reference and score as a 100% difference.
    """
    frame = body(image) if crop_body else image
    return {
        "body_diff": round(diff_fraction(frame, reference), 4),
        "bg_fraction": round(bg_fraction(frame), 4),
        "exact_bg": exact_bg_fraction(frame),
        "mean": round(float(ImageStat.Stat(frame.convert("L")).mean[0]), 2),
        "content_erased": content_erase_fraction(frame, reference),
        "size": list(image.size),
    }


def choose_probe_patch(reference_body: Image.Image) -> tuple[int, int, int, int]:
    """Pick the body patch that is least like the toplevel background.

    A blank frame paints the background colour everywhere, so the most sensitive
    probe is the patch that is normally *least* background-coloured - usually a
    row of labels or a filled input.  Returns ``(left, top, width, height)``
    relative to the body.
    """
    width, height = reference_body.size
    patch_width = min(PATCH_SIZE[0], width)
    patch_height = min(PATCH_SIZE[1], height)
    best: tuple[float, int, int] | None = None
    for top in range(0, max(height - patch_height, 0) + 1, PATCH_STEP):
        for left in range(0, max(width - patch_width, 0) + 1, PATCH_STEP):
            crop = reference_body.crop((left, top, left + patch_width, top + patch_height))
            fraction = bg_fraction(crop)
            if best is None or fraction < best[0]:
                best = (fraction, left, top)
    assert best is not None
    return (best[1], best[2], patch_width, patch_height)


def main() -> int:
    # Declared up front because ``--content-tolerance`` reads the constant as its
    # argparse default further down; Python rejects a ``global`` declaration that
    # appears after any use of the name in the same function.
    global CONTENT_TOLERANCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", default=os.path.join(ROOT, "dist", "CodexConfigTool.exe"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--wait-input", type=float, default=180.0)
    parser.add_argument("--sample-seconds", type=float, default=2.5)
    parser.add_argument(
        "--restore-via",
        choices=("taskbar", "api", "auto"),
        default="taskbar",
        help=(
            "how to trigger the restore; 'api' uses ShowWindow(SW_RESTORE) and is "
            "the control for whether the flash belongs to the taskbar path or to "
            "the window's own repaint on map"
        ),
    )
    parser.add_argument(
        "--probe",
        choices=("full", "patch"),
        default="full",
        help=(
            "what to capture each frame; 'patch' samples one small auto-chosen "
            "region and reaches several hundred frames per second, which turns "
            "flash detection from a coin toss into something reliable"
        ),
    )
    parser.add_argument(
        "--minimize-via",
        choices=("click", "api"),
        default="click",
        help=(
            "how to minimize before each restore; 'click' presses the app's own "
            "custom minimize button (synthetic input), 'api' uses "
            "ShowWindow(SW_MINIMIZE). With '--restore-via api --minimize-via api' "
            "the whole check needs no synthetic input at all"
        ),
    )
    parser.add_argument(
        "--probe-patch",
        default=None,
        help=(
            "force the probe region as LEFT,TOP in body coordinates instead of "
            "letting the harness pick the least-background patch. Use it to ask "
            "whether a region flashes at all: the auto-chosen patch sits in the "
            "dark sidebar, where a background-coloured frame is a 78%% difference, "
            "but a light region can flash just as hard and still score ~0 because "
            "the toplevel background and that region's background are the same "
            "colour"
        ),
    )
    parser.add_argument(
        "--content-tolerance",
        type=int,
        default=CONTENT_TOLERANCE,
        help=(
            f"per-channel distance from the toplevel background below which a "
            f"pixel counts as background when measuring content erasure "
            f"(default {CONTENT_TOLERANCE}). Must stay under 12, the distance to "
            f"the white card fill, or the card stops counting as content"
        ),
    )
    args = parser.parse_args()
    # Retune the content metric's tolerance everywhere at once.  This works at all
    # because ``content_mask`` resolves its default at call time; binding it as a
    # default argument would have frozen the value at import and silently ignored
    # this flag.
    CONTENT_TOLERANCE = args.content_tolerance
    threshold = PATCH_FRACTION if args.probe == "patch" else FLASH_FRACTION

    # The child is started with ``cwd=ROOT`` (the app directory), so a relative
    # ``--exe`` resolves against the app root rather than the caller's directory.
    # The child then dies immediately with "can't open file", but that line is
    # only one line of child output and the harness's own verdict says
    # "main window not found" - which misattributes a typo'd path to the build and
    # costs a full find_main_window timeout to discover.  Resolve it and fail fast.
    exe = os.path.abspath(args.exe)
    if not os.path.exists(exe):
        print(f"HARNESS --exe does not exist: {args.exe} (resolved to {exe})")
        return 2
    args.exe = exe

    os.makedirs(OUT_DIR, exist_ok=True)

    # Synthetic input is only needed to click the app's minimize button or the
    # taskbar button.  With an all-API cycle there is no click at all, so requiring
    # injection would waste up to --wait-input seconds and make the check
    # unrunnable on a session where injection is unavailable - for no reason.
    needs_input = args.minimize_via == "click" or args.restore_via != "api"
    if needs_input:
        injectable, detail = wait_for_input_injection(args.wait_input)
        if not injectable:
            print("ENVIRONMENT input injection unavailable: " + detail)
            return 3
    else:
        print("pre-flight: all-API cycle (minimize + restore); synthetic input not required")

    notes: list[str] = []
    failures: list[str] = []
    runs: list[dict] = []

    # The app holds a single-instance mutex, and the packaged build and a
    # source run share its name.  If a copy is already running the new process
    # only shows an "already running" message box and exits, so the harness would
    # wait out find_main_window's timeout and blame the build.  Clear the way
    # first, and say so.
    for name in ("CodexConfigTool.exe", os.path.basename(args.exe)):
        closed = close_existing_instances(name, notes)
        if closed:
            print(f"pre-flight: closed {closed} pre-existing {name} instance(s)")
    # A source run is ``python.exe``, so the image-name check above cannot see it;
    # match on the app's own window instead.
    closed = close_existing_app_windows(notes)
    if closed:
        print(f"pre-flight: closed {closed} process(es) owning an app window")

    # A ``.py`` path runs the app from source (used to trace the window code,
    # which the packaged build cannot be instrumented for).
    if args.exe.lower().endswith(".py"):
        command = [sys.executable, args.exe]
    else:
        command = [args.exe]

    pre = set(all_visible_windows())
    process = subprocess.Popen(command, cwd=ROOT)
    hwnd = 0
    pid = 0

    try:
        hwnd, pid = find_main_window(pre)
        if not hwnd:
            appeared = sorted(
                (W.class_name(h), W.window_text(h)[:40])
                for h in set(all_visible_windows()) - pre
            )
            print("main window not found; windows that did appear:")
            for cls, text in appeared:
                print(f"   {cls} {text!r}")
            if any(cls == "#32770" for cls, _ in appeared):
                print("   -> a message box appeared: another instance still owns the mutex")
            return 2
        time.sleep(2.5)
        if W.is_iconic(hwnd):
            # Nothing in this script has minimized anything yet, so another driver
            # (a leftover harness run) is acting on the same window.
            print("main window is already minimized before the first cycle")
            print("   -> another harness run is driving this window; not measuring")
            return 2
        print(f"window {hwnd:#x} pid={pid} {W.describe(hwnd)}")

        ensure_foreground(hwnd, notes, "reference")
        time.sleep(0.5)
        reference_image = grab.grab_window(hwnd)
        reference = body(reference_image)
        reference_image.save(os.path.join(OUT_DIR, "restore-flash-reference.png"))
        print(f"reference captured, body {reference.size[0]}x{reference.size[1]}")

        # Probe geometry, in screen coordinates (the window does not move).
        patch_left = patch_top = patch_width = patch_height = 0
        # The dark-frame threshold depends on the probe's own settled brightness,
        # so it is only known in patch mode; in full mode the reference itself is
        # the settled frame.
        probe_mean = round(float(ImageStat.Stat(reference.convert("L")).mean[0]), 2)
        dark_threshold = round(probe_mean - DARK_MARGIN, 2)
        if args.probe == "patch":
            if args.probe_patch:
                forced_left, forced_top = (
                    int(part) for part in args.probe_patch.split(",")
                )
                patch_width, patch_height = PATCH_SIZE
                body_width, body_height = reference.size
                patch_left = max(0, min(forced_left, body_width - patch_width))
                patch_top = max(0, min(forced_top, body_height - patch_height))
                print(
                    f"probe patch FORCED to body ({patch_left},{patch_top}) "
                    f"{patch_width}x{patch_height} (auto-choice overridden)"
                )
            else:
                patch_left, patch_top, patch_width, patch_height = choose_probe_patch(reference)
            rect = W.window_rect(hwnd)
            probe_x = rect[0] + patch_left
            probe_y = rect[1] + TITLE_BAR_HEIGHT + patch_top
            probe_reference = reference.crop(
                (patch_left, patch_top, patch_left + patch_width, patch_top + patch_height)
            )
            probe_reference.save(os.path.join(OUT_DIR, "restore-flash-probe-patch.png"))
            # The probe's own settled brightness, which is the only meaningful
            # baseline for "is this frame unpainted?" - see DARK_MARGIN.
            probe_mean = round(
                float(ImageStat.Stat(probe_reference.convert("L")).mean[0]), 2
            )
            dark_threshold = round(probe_mean - DARK_MARGIN, 2)
            print(
                f"probe patch {patch_width}x{patch_height} at body ({patch_left},{patch_top}) "
                f"screen ({probe_x},{probe_y}), background fraction "
                f"{bg_fraction(probe_reference):.3f}, settled mean {probe_mean} "
                f"(a frame below {dark_threshold} is an unpainted surface)"
            )
        # Idle CPU before any restore.  A compositing change can cost either a
        # one-off burst per restore (acceptable) or a *continuous* repaint loop
        # (not acceptable - it burns a core while the window just sits there), and
        # the per-restore figure alone cannot tell those apart.
        #
        # Sampled over several consecutive windows rather than one: a single window
        # cannot distinguish a steady burn from the decaying tail of the settle
        # after startup, and those two call for opposite decisions.
        idle_samples = []
        for window in range(IDLE_CPU_WINDOWS):
            window_before = W.process_cpu_seconds(pid)
            window_started = time.time()
            time.sleep(IDLE_CPU_SECONDS)
            window_after = W.process_cpu_seconds(pid)
            window_wall = time.time() - window_started
            if window_before is None or window_after is None:
                idle_samples.append(None)
                continue
            idle_samples.append(round(window_after - window_before, 4))
            print(
                f"idle cpu window {window + 1}: {idle_samples[-1]}s over "
                f"{window_wall:.1f}s of no restores"
            )
        # The steady-state figure is the *last* window, once any settle has passed.
        idle_cpu = idle_samples[-1] if idle_samples else None
        idle_wall = IDLE_CPU_SECONDS
        cpu_before = W.process_cpu_seconds(pid)
        cpu_started = time.time()
        for index in range(1, args.runs + 1):
            if W.is_iconic(hwnd):
                W.restore_window(hwnd)
                time.sleep(1.0)
            ensure_foreground(hwnd, notes, f"run{index} start")
            time.sleep(0.4)

            def minimize(label: str) -> bool:
                if args.minimize_via == "api":
                    W.minimize_window(hwnd)
                    time.sleep(1.5)
                    return W.is_iconic(hwnd)
                rect = W.window_rect(hwnd)
                click_app(
                    hwnd,
                    rect[0] + rect[2] - MINIMIZE_BUTTON_OFFSET,
                    rect[1] + TITLE_BAR_HEIGHT // 2,
                    label,
                    notes,
                )
                time.sleep(1.5)
                return W.is_iconic(hwnd)

            # 1. minimize, then locate the taskbar button from a normal/minimized pair.
            #    The button is only needed for a taskbar click, so an API restore
            #    skips the whole capture-and-diff, which also removes a failure mode
            #    that has nothing to do with the flash.
            if not minimize(f"run{index} minimize"):
                failures.append(f"run{index}: did not minimize")
                break
            if args.restore_via == "api":
                button, deltas = None, []
            else:
                minimized_strip = os.path.join(OUT_DIR, f"flash-run{index}-minimized-taskbar.png")
                grab.grab_taskbar_strip().save(minimized_strip)
                W.restore_window(hwnd)
                time.sleep(1.2)
                ensure_foreground(hwnd, notes, f"run{index} baseline")
                normal_strip = os.path.join(OUT_DIR, f"flash-run{index}-normal-taskbar.png")
                grab.grab_taskbar_strip().save(normal_strip)
                state_runs = changed_runs(minimized_strip, normal_strip, TASKBAR_SCAN)
                button, deltas = app_button(state_runs, normal_strip, minimized_strip)

            # 2. minimize again, then sample through the restore
            if not minimize(f"run{index} minimize again"):
                failures.append(f"run{index}: did not minimize the second time")
                break

            frames: list[dict] = []
            images: list[Image.Image] = []
            skipped = {"iconic": 0, "error": 0, "tiny": 0}
            restore_via = "api-fallback"

            def capture(seconds: float) -> None:
                """Sample the window as fast as the machine allows.

                Frames captured while the window is still iconic are dropped: a
                minimized window reports the off-screen placeholder rect
                (~-32000,-32000), so BitBlt there returns nothing and the frame
                would score as a 100% difference - a false flash.  The loop spins
                rather than sleeping so the first painted frame is not missed.
                """
                deadline = time.time() + seconds
                while time.time() < deadline:
                    started = time.time()
                    if W.is_iconic(hwnd):
                        skipped["iconic"] += 1
                        continue
                    try:
                        if args.probe == "patch":
                            shot = grab.grab_rect(
                                probe_x, probe_y, patch_width, patch_height
                            )
                        else:
                            shot = grab.grab_window(hwnd)
                    except Exception:  # noqa: BLE001 - window not up yet
                        skipped["error"] += 1
                        continue
                    if shot.width < 100 or shot.height < 100:
                        skipped["tiny"] += 1
                        continue
                    record = score(
                        shot,
                        probe_reference if args.probe == "patch" else reference,
                        crop_body=args.probe != "patch",
                    )
                    record["t_ms"] = round((started - start) * 1000, 1)
                    # These probes are what makes each frame cost ~20 ms, and a
                    # cheap frame rate matters more than per-frame detail when
                    # hunting a flash that can be a single frame long.  In patch
                    # mode they are sampled every tenth frame instead.
                    if args.probe == "full" or len(frames) % 10 == 0:
                        # A style change on re-map would mean the app called
                        # SetWindowPos(SWP_FRAMECHANGED), which recalculates the
                        # frame and invalidates the whole window.
                        style = W.get_style(hwnd)
                        record["style"] = hex(style)
                        record["minbox"] = bool(style & W.WS_MINIMIZEBOX)
                        record["frame"] = list(W.frame_thickness(hwnd))
                        # If the rect moves, the frame is showing whatever is behind
                        # the window rather than an undrawn window.
                        rect = W.window_rect(hwnd)
                        record["rect"] = list(rect)
                        record["dwm"] = (
                            list(bounds) if (bounds := W.dwm_frame_bounds(hwnd)) else None
                        )
                        record["top_class"] = W.class_name(
                            W.root_at((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
                        )
                    frames.append(record)
                    images.append(shot)

            start = time.time()
            restore_epoch = start
            if button and args.restore_via != "api":
                bbox = bbox_of(button)
                W.pin_on_top(hwnd, False)
                click_taskbar_bbox(bbox, notes, f"run{index} restore")
                capture(args.sample_seconds)
                time.sleep(0.3)
                if not W.is_iconic(hwnd):
                    restore_via = "taskbar-click"
            else:
                W.pin_on_top(hwnd, False)
                W.restore_window(hwnd)
                restore_via = "api"
                capture(args.sample_seconds)
                time.sleep(0.3)
            if W.is_iconic(hwnd):
                W.restore_window(hwnd)
                time.sleep(1.0)
                if restore_via == "taskbar-click":
                    restore_via = "taskbar-click-then-api"

            settled = score(grab.grab_window(hwnd), reference)
            # A metric with no noise floor cannot support any conclusion drawn from
            # it, and this project has already published one result that was really
            # just sampling noise.  The settled frame is the reference, so it must
            # score ~0; if it does not, say so rather than reporting the run.
            if (settled.get("content_erased") or 0.0) > 0.05:
                notes.append(
                    f"run{index}: the settled frame scores "
                    f"content_erased={settled['content_erased']:.2f} against the "
                    "reference it was compared with - the metric has no noise "
                    "floor here and this run's numbers should not be trusted"
                )
            worst_index = max(range(len(frames)), key=lambda i: frames[i]["body_diff"]) if frames else None
            worst = frames[worst_index] if worst_index is not None else None
            offenders = [f for f in frames if f["body_diff"] > threshold]
            # The content metric, reported separately because it is not gated on:
            # ``body_diff`` answers "did this region change", which depends on how
            # dense the region is, while ``content_erased`` answers "did this frame
            # wipe out what was there", which does not.  Keeping both visible is
            # what lets a sidebar run and a content-area run be compared directly.
            worst_erase = max((f.get("content_erased") or 0.0 for f in frames), default=0.0)
            erase_offenders = [
                f for f in frames
                if (f.get("content_erased") or 0.0) > CONTENT_ERASE_FRACTION
            ]
            if worst_index is not None:
                images[worst_index].save(os.path.join(OUT_DIR, f"restore-flash-worst-run{index}.png"))
            # Keep the offending frames themselves - they are the evidence.
            for order, offender in enumerate(offenders[:3], start=1):
                position = frames.index(offender)
                images[position].save(
                    os.path.join(OUT_DIR, f"restore-flash-offender-run{index}-{order}.png")
                )
                offender["saved_as"] = f"restore-flash-offender-run{index}-{order}.png"

            entry = {
                "run": index,
                "restore_via": restore_via,
                "minimize_via": args.minimize_via,
                "frames": len(frames),
                "skipped": skipped,
                "first_frame_ms": frames[0]["t_ms"] if frames else None,
                "sample_span_ms": frames[-1]["t_ms"] if frames else None,
                # Absolute epoch of the restore call.  ``t_ms`` is relative to
                # this, so recording it lets the app's own trace (which stamps
                # ``time.time()``) be lined up with the frame timeline on the
                # same machine clock.
                "restore_epoch": restore_epoch,
                "styles_seen": sorted({f["style"] for f in frames if "style" in f}),
                "frames_seen": sorted({tuple(f["frame"]) for f in frames if "frame" in f}),
                "distinct_rects": len(
                    {tuple(f["rect"]) for f in frames if "rect" in f}
                ),
                "rects_seen": sorted({tuple(f["rect"]) for f in frames if "rect" in f})[:6],
                "dwm_mismatch_frames": sum(
                    1 for f in frames if f.get("dwm") and tuple(f["dwm"]) != tuple(f["rect"])
                ),
                "worst": worst,
                "frames_over_threshold": len(offenders),
                "worst_content_erased": round(worst_erase, 4),
                "content_erase_frames": len(erase_offenders),
                "settled": settled,
                "alive": process_alive(pid),
                "timeline": frames,
            }
            runs.append(entry)
            print(
                "[run] "
                + json.dumps(
                    {k: v for k, v in entry.items() if k not in ("worst", "timeline")},
                    ensure_ascii=False,
                )
            )
            if worst:
                print("      worst " + json.dumps(worst, ensure_ascii=False))

            if offenders:
                failures.append(
                    f"run{index}: {len(offenders)} frame(s) differ from the settled UI by "
                    f"more than {threshold:.0%} (worst {worst['body_diff']:.1%}, "
                    f"bg {worst['bg_fraction']:.1%}, mean {worst['mean']})"
                )

        # Computed before the report literal, because the aggregate block below is
        # evaluated as part of that literal and cannot refer to it yet.
        cpu_after = W.process_cpu_seconds(pid)
        cpu_delta = (
            round(cpu_after - cpu_before, 4)
            if cpu_before is not None and cpu_after is not None
            else None
        )
        cpu_per_restore = (
            round(cpu_delta / len(runs), 4) if cpu_delta is not None and runs else None
        )
        report = {
            "exe": args.exe,
            "variant": os.environ.get("CODEX_VARIANT"),
            "probe": args.probe,
            "threshold": threshold,
            "content_tolerance": CONTENT_TOLERANCE,
            # The app's own CPU cost over the measured window.  A compositing
            # change can present the same frames while working much harder, which
            # no frame metric can see - so it is reported next to them.
            "cpu": {
                "before": cpu_before,
                "after": cpu_after,
                "wall_seconds": round(time.time() - cpu_started, 2),
                "runs": len(runs),
                "idle_seconds": round(idle_wall, 2),
                "idle_cpu_seconds": idle_cpu,
                "idle_cpu_samples": idle_samples,
            },
            "probe_patch": (
                {
                    "body": [patch_left, patch_top, patch_width, patch_height],
                    "background_fraction": round(bg_fraction(probe_reference), 4),
                }
                if args.probe == "patch"
                else None
            ),
            "reference": score(reference_image, reference),
            "runs": runs,
            # Aggregate numbers so a caller does not have to re-derive them.  The
            # flash is a known, accepted characteristic of this window, so the
            # useful signal is not "did it flash" but "how often and how long",
            # compared against the recorded baseline (94% of restores, 2.4 bad
            # frames per restore - see AGENT_HANDOFF_WINDOW_BUGS.md).
            "aggregate": {
                "runs": len(runs),
                "runs_flashing": sum(1 for r in runs if r["frames_over_threshold"]),
                "bad_frames": sum(r["frames_over_threshold"] for r in runs),
                "bad_frames_per_run": round(
                    sum(r["frames_over_threshold"] for r in runs) / len(runs), 2
                )
                if runs
                else None,
                # A frame darker than the *settled probe* means an unpainted surface
                # reached the screen, which is a worse artefact than a light blank.
                # This used to be ``mean < 200``, a constant that is meaningless for
                # a dark probe: the sidebar patch settles at ``mean 126.26``, so a
                # partial blank at ``mean 168.5`` is 42 units *lighter* than the
                # settled UI and was counted as darker than it.  Compare against the
                # probe's own brightness, and scan the whole timeline rather than
                # only the max-body_diff frame - an unpainted surface is a defect
                # whether or not it also happens to be the biggest difference.
                "frames_darker_than_ui": sum(
                    1
                    for r in runs
                    for f in (r.get("timeline") or [])
                    if f.get("mean") is not None and f["mean"] < dark_threshold
                ),
                "dark_threshold": dark_threshold,
                "probe_mean": probe_mean,
                "dark_margin": DARK_MARGIN,
                # The app's own CPU cost, so a change that presents the same frames
                # by working harder is still visible.  Reported per restore so runs
                # with different N are comparable.
                "cpu_seconds": cpu_delta,
                "cpu_seconds_per_restore": cpu_per_restore,
                "idle_cpu_seconds": idle_cpu,
                "idle_cpu_per_second": (
                    round(idle_cpu / idle_wall, 4) if idle_cpu is not None and idle_wall else None
                ),
                # Region-independent view of the same event, so a run whose probe
                # sits in a sparse area is still comparable with one in the sidebar.
                "content_tolerance": CONTENT_TOLERANCE,
                "worst_content_erased": round(
                    max((r["worst_content_erased"] for r in runs), default=0.0), 4
                ),
                "content_erase_frames": sum(r["content_erase_frames"] for r in runs),
                "runs_content_erasing": sum(
                    1 for r in runs if r["content_erase_frames"]
                ),
                # Which mechanism the erasing frames were made of.  1.0 means the
                # frame was entirely the toplevel's own background; 0.0 means it was
                # light but *not* that colour, i.e. the window was showing what is
                # behind it.  Both read mean ~244, so brightness cannot distinguish
                # them - see exact_bg_fraction().
                "worst_erase_exact_bg": round(
                    max(
                        (
                            f.get("exact_bg") or 0.0
                            for r in runs
                            for f in (r.get("timeline") or [])
                            if (f.get("content_erased") or 0.0) > CONTENT_ERASE_FRACTION
                        ),
                        default=0.0,
                    ),
                    4,
                ),
            },
            "failures": failures,
            "interaction_notes": notes,
        }
        path = os.path.join(OUT_DIR, "restore-flash-report.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print("REPORT " + path)
        cost = report["aggregate"].get("cpu_seconds_per_restore")
        if cost is not None:
            print(
                f"cpu   {cost}s per restore "
                f"({report['aggregate']['cpu_seconds']}s over {len(runs)} restore(s), "
                f"{report['cpu']['wall_seconds']}s wall)"
            )
        verdict = "PASS" if not failures else "FAIL"
        print(
            "SUMMARY "
            + json.dumps(
                {
                    "verdict": verdict,
                    "aggregate": report["aggregate"],
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
        for target in (pid, process.pid):
            if target:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(target)],
                    capture_output=True,
                    check=False,
                )


if __name__ == "__main__":
    raise SystemExit(main())
