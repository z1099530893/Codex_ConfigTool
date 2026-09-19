"""Drive a minimize/restore cycle and measure the blank frame - in Tk and in Qt.

Why this exists
---------------
``proto_surface_count.py`` measured the structural difference between the two
frameworks: the *same* UI tree is 52 native windows in Tk and 1 in Qt.  This
script measures the consequence of that difference, so the causal claim stops
being an inference.

The two programs under test are built by ``proto_surface_count.py``: identical
nesting, identical widget count, identical colours (dark sidebar ``#1e1f22``
on the left 142 px, light content ``#f3f4f7``), identical size (820x500).  The
only variable is the toolkit.  The driver, the probe geometry, the cycle timing
and the scoring are the same for both.

What is measured
----------------
A thin horizontal strip near the bottom of the window, wide enough to cross
*inside the dark sidebar* and *into the light content area*:

    +--------------------------------------------------+
    |  title bar                                        |
    +---------+----------------------------------------+
    | sidebar |  content                               |
    | (dark)  |  (light)                               |
    |         |                                        |
    |         |                                        |
    | ########|#####################   <-- probe strip |
    +---------+----------------------------------------+
      x 1..141        x 146..300

On restore the interesting question is whether the sidebar is ever presented
*paler than itself* - i.e. whether a frame is composed in which the window's
own background is showing where the dark sidebar should be.  That is the
flicker: measured on the real app as ``mean 244.0`` over a region that settles
at ``126.26``.

Scoring
-------
``sidebar_blank``  a frame whose sidebar mean is more than ``--margin`` above
                   the settled sidebar mean.  This is the flicker.
``content_dark``   a frame whose content mean is more than ``--margin`` below
                   the settled content mean.  The mirror image, and a check
                   that the probe is not simply reacting to "anything changed".

A frame counter cannot see cost, and a threshold that is a constant is wrong
the moment the region changes - so the threshold here is relative to the
measured settled value, and the settled value is printed.

Usage
-----
    python proto_restore_flash.py --framework tk
    python proto_restore_flash.py --framework qt
    python proto_restore_flash.py --both

Needs ``proto_surface_count.py`` and ``winapi.py`` beside it, plus Pillow.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import winapi as W  # noqa: E402

from PIL import Image, ImageGrab  # noqa: E402

import grab as G  # noqa: E402

SETTLE_SECONDS = 0.9
STRIP_REL_TOP = 440
STRIP_HEIGHT = 8
STRIP_WIDTH = 300
SIDEBAR_STRIP = (1, 141)
CONTENT_STRIP = (146, 299)

# Validity bounds for the positive control and the per-cycle ``probe_valid``
# guard.  These defaults describe the prototype UIs, whose sidebar is
# ``#1e1f22``.  The real application's sidebar is ``#5b5b5b`` (mean ~91) and its
# flat sidebar strip sits higher up, so both are command-line overridable
# instead of baked in.  A blanked frame reads the toplevel background
# (``#f3f4f7``, mean ~244) in either case, so the gap stays wide.
SIDEBAR_MAX = 90.0
CONTENT_MIN = 180.0

WS_EX_COMPOSITED = 0x02000000

WINDOW_X, WINDOW_Y = 90, 90
WINDOW_W, WINDOW_H = 820, 500


# ------------------------------------------------------------- fast sampling
# ``ImageGrab.grab`` and even a fresh ``BitBlt`` per call cost ~16-33 ms, which
# is the same order as the event being measured - so they can only report
# "a blank frame existed", not how long it lasted.  For duration the sampler has
# to be at least an order of magnitude faster than the thing it is watching.
#
# Reusing one memory DC and one top-down 32-bpp ``CreateDIBSection`` does that:
# the DIB hands back a pointer to its own pixels, so a sample is one ``BitBlt``
# plus a read of ~9.6 KB of already-mapped memory, with no per-frame allocation,
# no ``GetDIBits`` and no PIL object.
# Handle-returning GDI calls need explicit restypes.  Without them ctypes
# assumes ``c_int`` and truncates the handle to 32 bits - the same trap that
# makes an untended ``OpenProcess`` + ``CloseHandle`` kill a process silently.
G.gdi32.CreateDIBSection.argtypes = (
    G.wintypes.HDC,
    ctypes.c_void_p,
    G.wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    G.wintypes.HANDLE,
    G.wintypes.DWORD,
)
G.gdi32.CreateDIBSection.restype = G.wintypes.HBITMAP
G.gdi32.CreateCompatibleDC.argtypes = (G.wintypes.HDC,)
G.gdi32.CreateCompatibleDC.restype = G.wintypes.HDC
G.gdi32.SelectObject.argtypes = (G.wintypes.HDC, G.wintypes.HGDIOBJ)
G.gdi32.SelectObject.restype = G.wintypes.HGDIOBJ
G.user32.GetDC.argtypes = (G.wintypes.HWND,)
G.user32.GetDC.restype = G.wintypes.HDC
G.user32.ReleaseDC.argtypes = (G.wintypes.HWND, G.wintypes.HDC)
G.user32.ReleaseDC.restype = ctypes.c_int


class FastSampler:
    """Repeatedly sample one screen rectangle as fast as GDI allows."""

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y = int(x), int(y)
        self.width, self.height = int(width), int(height)
        self.screen_dc = G.user32.GetDC(None)
        self.mem_dc = G.gdi32.CreateCompatibleDC(self.screen_dc)

        info = G.BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(G.BITMAPINFOHEADER)
        info.bmiHeader.biWidth = self.width
        info.bmiHeader.biHeight = -self.height  # negative = top-down rows
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0  # BI_RGB

        self.bits = ctypes.c_void_p()
        self.bitmap = G.gdi32.CreateDIBSection(
            self.screen_dc,
            ctypes.byref(info),
            0,
            ctypes.byref(self.bits),
            None,
            0,
        )
        G.gdi32.SelectObject(self.mem_dc, self.bitmap)
        self.buffer = (ctypes.c_ubyte * (self.width * self.height * 4)).from_address(
            self.bits.value
        )

    def sample(self) -> bytes:
        G.gdi32.BitBlt(
            self.mem_dc,
            0,
            0,
            self.width,
            self.height,
            self.screen_dc,
            self.x,
            self.y,
            G.SRCCOPY | G.CAPTUREBLT,
        )
        return bytes(self.buffer)

    def region_mean(self, raw: bytes, x0: int, x1: int) -> float:
        """Mean of the RGB bytes (alpha skipped) in columns x0..x1, all rows."""
        total = 0
        stride = self.width * 4
        for row in range(self.height):
            base = row * stride
            for column in range(x0, x1):
                offset = base + column * 4
                total += raw[offset] + raw[offset + 1] + raw[offset + 2]
        return total / (3 * (x1 - x0) * self.height)

    def to_image(self, raw: bytes) -> Image.Image:
        return Image.frombytes("RGBA", (self.width, self.height), raw).convert("RGB")

    def close(self) -> None:
        try:
            G.gdi32.DeleteObject(self.bitmap)
            G.gdi32.DeleteDC(self.mem_dc)
            G.user32.ReleaseDC(None, self.screen_dc)
        except Exception:
            pass


# --------------------------------------------------------------------- win32
_user32 = ctypes.windll.user32
_user32.SetWindowPos.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint,
]
_user32.SetWindowPos.restype = ctypes.c_int
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


def place_window(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    _user32.SetWindowPos(
        ctypes.c_void_p(hwnd), None, x, y, width, height,
        SWP_NOZORDER | SWP_NOACTIVATE,
    )


SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_FRAMECHANGED = 0x0020


def apply_composited(hwnd: int) -> dict:
    """Set ``WS_EX_COMPOSITED`` from outside the process that owns the window.

    Cross-process ``SetWindowLongPtr(GWL_EXSTYLE)`` is fine; what is *not* fine
    is applying this to a window owned by the process that is currently in the
    foreground - that terminates the caller.  The driver is a separate process
    and is not the owner, so this is the safe direction.

    ``SWP_FRAMECHANGED`` is what makes the new style take effect; without it the
    bit is stored and ignored.
    """
    before = W.get_ex_style(hwnd)
    W.set_ex_style(hwnd, before | WS_EX_COMPOSITED)
    _user32.SetWindowPos(
        ctypes.c_void_p(hwnd), None, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )
    time.sleep(0.4)
    after = W.get_ex_style(hwnd)
    return {
        "before": f"0x{before:08X}",
        "after": f"0x{after:08X}",
        "applied": bool(after & WS_EX_COMPOSITED),
    }


# --------------------------------------------------------------------- probe
def strip_bbox(hwnd: int) -> tuple[int, int, int, int]:
    """Screen rect of the whole window - the capture region.

    Capturing the whole window rather than a thin strip costs frame rate, but
    it means every measured frame is also an *image* of the event, and a metric
    you cannot look at is a metric you will eventually misread.  The strip
    statistics are derived by cropping this.
    """
    left, top, width, height = W.window_rect(hwnd)
    return (left, top, left + width, top + height)


def _mean(chunk) -> float:
    """Mean byte value of an RGB crop.  Bytes, not ``getdata`` - this runs
    thousands of times inside a 500 ms capture window."""
    data = chunk.convert("RGB").tobytes()
    return sum(data) / len(data)


def measure(image) -> tuple[float, float]:
    """Return (sidebar_mean, content_mean) from a whole-window capture.

    The probe strip sits near the bottom of the window, where the sidebar has
    run out of nav buttons and the content area has run out of cards - so both
    halves are plain background, and any deviation is the window failing to
    paint rather than a widget changing.
    """
    sidebar = image.crop(
        (
            SIDEBAR_STRIP[0],
            STRIP_REL_TOP,
            SIDEBAR_STRIP[1],
            STRIP_REL_TOP + STRIP_HEIGHT,
        )
    )
    content = image.crop(
        (
            CONTENT_STRIP[0],
            STRIP_REL_TOP,
            CONTENT_STRIP[1],
            STRIP_REL_TOP + STRIP_HEIGHT,
        )
    )
    return _mean(sidebar), _mean(content)


def run_framework(
    framework: str,
    cycles: int,
    capture_seconds: float,
    margin: float,
    debug: bool = False,
    save_all: bool = False,
    capture: str = "strip",
    composited: bool = False,
) -> dict:
    if framework == "qt-app":
        # The shipping Qt window: same construction flags, same widget tree,
        # same style sheet as ``codex_config_qt``.
        command = [sys.executable, os.path.join(HERE, "serve_qt_app.py")]
    elif framework == "qt-exe":
        # The packaged artifact.  Not interchangeable with ``qt-app``: the source
        # window has no native children and the packaged one was measured with
        # two, and the native-child count is the property this probe exists to
        # measure.  Measuring only the source build leaves the shipped build's
        # restore behaviour unverified.
        command = [sys.executable, os.path.join(HERE, "serve_qt_exe.py")]
    elif framework == "tk-app":
        # The shipping Tk window - the "before" side, on the real program.
        command = [sys.executable, os.path.join(HERE, "serve_tk_app.py")]
    else:
        command = [
            sys.executable,
            os.path.join(HERE, "proto_surface_count.py"),
            f"--{framework}",
            "--serve",
        ]
    server = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=HERE,
    )
    report: dict = {"framework": framework, "cycles": []}
    try:
        hwnd = _await_hwnd(server, timeout=40.0)
        if not hwnd:
            report["error"] = "no hwnd from server"
            return report

        place_window(hwnd, WINDOW_X, WINDOW_Y, WINDOW_W, WINDOW_H)
        time.sleep(0.4)
        W.raise_window(hwnd)
        W.make_foreground(hwnd, timeout=3.0)
        time.sleep(0.5)

        left, top, width, height = W.window_rect(hwnd)
        report["window"] = {
            "hwnd": f"{hwnd:#x}",
            "class": W.class_name(hwnd),
            "rect": [left, top, width, height],
            "style": f"0x{W.get_style(hwnd):08X}",
            "exstyle": f"0x{W.get_ex_style(hwnd):08X}",
            "native_descendants": len(W.child_windows(hwnd)),
        }
        if composited:
            report["composited"] = apply_composited(hwnd)
            place_window(hwnd, WINDOW_X, WINDOW_Y, WINDOW_W, WINDOW_H)
            time.sleep(0.4)
            W.raise_window(hwnd)
            W.make_foreground(hwnd, timeout=3.0)
            time.sleep(0.5)
            left, top, width, height = W.window_rect(hwnd)
            report["window"]["exstyle"] = f"0x{W.get_ex_style(hwnd):08X}"

        bbox = strip_bbox(hwnd)
        report["probe_bbox"] = list(bbox)

        if debug:
            _dump_probe_debug(framework, hwnd, bbox, report)
            return report

        # Positive control: if the strip is not where we think it is, the
        # sidebar half will not read dark, and every number below is noise.
        # Positioning is not instantaneous - the window may still be settling -
        # so retry rather than declaring the probe broken on the first read.
        sidebar_ref = content_ref = None
        attempts = 0
        for attempts in range(1, 6):
            place_window(hwnd, WINDOW_X, WINDOW_Y, WINDOW_W, WINDOW_H)
            time.sleep(0.3)
            W.raise_window(hwnd)
            W.make_foreground(hwnd, timeout=3.0)
            time.sleep(0.4)
            reference = ImageGrab.grab(bbox=bbox)
            sidebar_ref, content_ref = measure(reference)
            if sidebar_ref <= SIDEBAR_MAX and content_ref >= CONTENT_MIN:
                break
        report["reference"] = {
            "sidebar_mean": round(sidebar_ref, 2),
            "content_mean": round(content_ref, 2),
            "attempts": attempts,
        }
        if sidebar_ref > SIDEBAR_MAX or content_ref < CONTENT_MIN:
            report["error"] = (
                f"positive control failed after {attempts} attempt(s): probe reads "
                f"sidebar {sidebar_ref:.1f} (want dark, <{SIDEBAR_MAX:.0f}) and content "
                f"{content_ref:.1f} (want light, >{CONTENT_MIN:.0f}) - probe is mispositioned"
            )
            return report

        if capture == "window":
            # Slow (~34 ms/frame) but every frame is a full-window image.  Use
            # this to *see* the event, not to time it.
            def take():
                return ImageGrab.grab(bbox=bbox)

            def means(sample):
                return measure(sample)

            def as_image(sample):
                return sample
        else:
            # Fast (a few ms/frame) but the frames are only the probe strip.
            # Use this to time the event.
            sampler = FastSampler(
                left + SIDEBAR_STRIP[0],
                top + STRIP_REL_TOP,
                STRIP_WIDTH,
                STRIP_HEIGHT,
            )

            def take():
                return sampler.sample()

            def means(sample):
                return (
                    sampler.region_mean(sample, SIDEBAR_STRIP[0], SIDEBAR_STRIP[1]),
                    sampler.region_mean(sample, CONTENT_STRIP[0], CONTENT_STRIP[1]),
                )

            def as_image(sample):
                image = sampler.to_image(sample)
                return image.resize(
                    (image.width * 3, image.height * 12), resample=0
                )

        for index in range(cycles):
            if not W.minimize_window(hwnd):
                report["error"] = f"minimize failed on cycle {index}"
                return report
            time.sleep(SETTLE_SECONDS)
            if not W.is_iconic(hwnd):
                report["error"] = f"window not iconic on cycle {index}"
                return report

            started = time.perf_counter()
            W.restore_window(hwnd)
            frames = []
            deadline = started + capture_seconds
            while time.perf_counter() < deadline:
                stamp = time.perf_counter() - started
                frames.append((stamp, take()))
            time.sleep(0.7)

            pairs = [means(sample) for _stamp, sample in frames]
            sidebar_values = [pair[0] for pair in pairs]
            content_values = [pair[1] for pair in pairs]
            settled = statistics.median(sidebar_values[-5:])
            content_settled = statistics.median(content_values[-5:])
            blank = [
                (round(stamp * 1000, 1), round(value, 1))
                for (stamp, _frame), value in zip(frames, sidebar_values)
                if value > settled + margin
            ]
            dark = [
                (round(stamp * 1000, 1), round(value, 1))
                for (stamp, _frame), value in zip(frames, content_values)
                if value < content_settled - margin
            ]

            # Save the worst frame of the cycle.  A number can be misread; an
            # image cannot.  This is the artifact that settles what "blank"
            # actually looked like on this machine, on this run.
            worst_index = max(range(len(frames)), key=lambda i: sidebar_values[i])
            worst_path = os.path.join(
                HERE, "out", f"worst-frame-{framework}-cycle{index}.png"
            )
            os.makedirs(os.path.dirname(worst_path), exist_ok=True)
            as_image(frames[worst_index][1]).save(worst_path)

            if save_all and index == 0:
                sequence_dir = os.path.join(HERE, "out", f"sequence-{framework}")
                os.makedirs(sequence_dir, exist_ok=True)
                for position, (stamp, sample) in enumerate(frames):
                    as_image(sample).save(
                        os.path.join(
                            sequence_dir,
                            f"{position:02d}_{stamp * 1000:06.1f}ms.png",
                        )
                    )

            interval_ms = (
                1000 * (frames[-1][0] - frames[0][0]) / max(len(frames) - 1, 1)
                if len(frames) > 1
                else None
            )

            # Second positive control, and the one that matters most: the probe
            # must still read the colours the UI actually has.  A change that
            # stops the window painting altogether makes the sidebar settle at
            # the wrong value, and a threshold measured *relative* to that
            # settled value then reports a flawless zero.  That is a masked
            # failure, not a fix - so validate before counting.
            probe_valid = settled <= SIDEBAR_MAX and content_settled >= CONTENT_MIN
            if not probe_valid:
                blank = []
                dark = []

            # Duration, not just presence.  A frame counter at 33 ms sampling can
            # only say "there was a blank frame"; with a few-ms sampler the
            # length of the unpainted interval becomes a number that can be
            # compared between architectures.
            blank_stamps = [stamp for (stamp, _s), value in zip(frames, sidebar_values)
                            if value > settled + margin]
            unpainted_ms = (
                round((blank_stamps[-1] - blank_stamps[0]) * 1000, 1)
                if blank_stamps
                else 0.0
            )
            # First sample after the last blank that is back to settled: the
            # moment the window can be said to be fully painted again.
            resolved_ms = None
            if blank_stamps:
                last_blank = blank_stamps[-1]
                for stamp, value in zip(
                    (s for s, _v in frames), sidebar_values
                ):
                    if stamp > last_blank and value <= settled + margin:
                        resolved_ms = round(stamp * 1000, 1)
                        break

            report["cycles"].append(
                {
                    "cycle": index,
                    "frames": len(frames),
                    "sidebar_settled": round(settled, 2),
                    "content_settled": round(content_settled, 2),
                    "sidebar_blank_frames": len(blank),
                    "sidebar_blank_detail": blank,
                    "content_dark_frames": len(dark),
                    "content_dark_detail": dark,
                    "sidebar_max": round(max(sidebar_values), 2),
                    "probe_valid": probe_valid,
                    "unpainted_span_ms": unpainted_ms,
                    "resolved_at_ms": resolved_ms,
                    "worst_frame": os.path.relpath(worst_path, HERE).replace("\\", "/"),
                    "worst_frame_stamp_ms": round(frames[worst_index][0] * 1000, 1),
                    "frame_interval_ms": round(interval_ms, 2)
                    if interval_ms is not None
                    else None,
                }
            )
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return report


def _dump_probe_debug(framework: str, hwnd: int, bbox: tuple, report: dict) -> None:
    """Save what the probe actually sees, and profile the strip.

    A probe that reads the wrong pixels produces a confident wrong answer, so
    when the positive control fires, look at the image instead of guessing.
    """
    out_dir = os.path.join(HERE, "out")
    os.makedirs(out_dir, exist_ok=True)

    screen = ImageGrab.grab()
    screen.save(os.path.join(out_dir, f"probe-debug-{framework}-screen.png"))
    strip = ImageGrab.grab(bbox=bbox)
    strip = strip.resize((strip.width * 3, strip.height * 12), resample=0)
    strip.save(os.path.join(out_dir, f"probe-debug-{framework}-strip.png"))

    left, top, width, height = report["window"]["rect"]
    window_crop = screen.crop((left, top, left + width, top + height))
    window_crop.save(os.path.join(out_dir, f"probe-debug-{framework}-window.png"))

    # Profile the *probe band*, not the whole window.  Averaging the full
    # window height mixes in the donation QR code and the selected nav row and
    # reads ~120 where the band itself is a flat 91 - which is exactly the kind
    # of confidently wrong number this dump exists to catch.
    band = ImageGrab.grab(
        bbox=(
            left,
            top + STRIP_REL_TOP,
            left + width,
            top + STRIP_REL_TOP + STRIP_HEIGHT,
        )
    ).convert("RGB")
    blocks = []
    for start in range(0, band.width, 20):
        chunk = band.crop((start, 0, min(start + 20, band.width), band.height))
        blocks.append(round(_mean(chunk), 1))
    report["debug"] = {
        "screen_size": list(screen.size),
        "window_rect": [left, top, width, height],
        "strip_top": STRIP_REL_TOP,
        "strip_profile_20px_blocks": blocks,
        "saved": [
            f"out/probe-debug-{framework}-screen.png",
            f"out/probe-debug-{framework}-window.png",
            f"out/probe-debug-{framework}-strip.png",
        ],
    }
    print(
        f"debug: screen={screen.size} window={[left, top, width, height]} "
        f"strip_top={STRIP_REL_TOP} strip profile (20px blocks)={blocks}",
        file=sys.stderr,
    )


def _await_hwnd(server: subprocess.Popen, timeout: float) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = server.stdout.readline()
        if not line:
            return 0
        if line.startswith("SERVE_HWND="):
            return int(line.split("=", 1)[1].strip(), 16)
    return 0


# ---------------------------------------------------------------------- main
def main() -> int:
    global STRIP_REL_TOP, SIDEBAR_MAX, CONTENT_MIN

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--framework",
        choices=["tk", "tk-canvas", "tk-canvas-composited", "qt", "qt-app", "qt-exe", "tk-app"],
        help=(
            "qt = the prototype stand-in; qt-app = the shipping Qt window from "
            "source; qt-exe = the packaged dist/CodexConfigTool-Qt.exe"
        ),
    )
    parser.add_argument("--both", action="store_true")
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--capture-seconds", type=float, default=0.5)
    parser.add_argument(
        "--margin",
        type=float,
        default=25.0,
        help="how far from the settled mean a frame must be to count",
    )
    parser.add_argument("--out", default=os.path.join(HERE, "out", "restore-flash.json"))
    parser.add_argument(
        "--debug",
        action="store_true",
        help="save what the probe sees and profile the strip, then stop",
    )
    parser.add_argument(
        "--save-all",
        action="store_true",
        help="save every captured frame of the first cycle, to inspect the sequence",
    )
    parser.add_argument(
        "--composited",
        action="store_true",
        help="apply WS_EX_COMPOSITED to the served window before measuring",
    )
    parser.add_argument(
        "--capture",
        choices=["strip", "window"],
        default="strip",
        help="strip = fast BitBlt probe, good for timing; "
        "window = full-window image per frame, good for looking at",
    )
    parser.add_argument(
        "--strip-top",
        type=int,
        default=STRIP_REL_TOP,
        help="probe strip offset from the window top; pick a vertically flat "
        "band, since a band crossing a selected nav row or an image reads noise",
    )
    parser.add_argument(
        "--sidebar-max",
        type=float,
        default=SIDEBAR_MAX,
        help="highest sidebar mean still considered 'painted'",
    )
    parser.add_argument(
        "--content-min",
        type=float,
        default=CONTENT_MIN,
        help="lowest content mean still considered 'painted'",
    )
    args = parser.parse_args()

    STRIP_REL_TOP = args.strip_top
    SIDEBAR_MAX = args.sidebar_max
    CONTENT_MIN = args.content_min

    targets = ["tk", "tk-canvas", "tk-canvas-composited", "qt", "qt-app"] if args.both else [args.framework]
    if not targets or targets == [None]:
        parser.error("pass --framework tk|tk-canvas|tk-canvas-composited|qt|qt-app or --both")

    reports = []
    for framework in targets:
        report = run_framework(
            framework,
            args.cycles,
            args.capture_seconds,
            args.margin,
            args.debug,
            args.save_all,
            args.capture,
            args.composited,
        )
        reports.append(report)
        _print_report(report)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(reports, handle, indent=2)

    if len(reports) >= 2 and all("error" not in r for r in reports):
        print("", file=sys.stderr)
        print("=== verdict ===", file=sys.stderr)
        for report in reports:
            valid = [c for c in report["cycles"] if c.get("probe_valid", True)]
            invalid = len(report["cycles"]) - len(valid)
            blanks = sum(c["sidebar_blank_frames"] for c in valid)
            total = sum(c["frames"] for c in valid)
            note = ""
            if invalid:
                note = f"  [{invalid} INVALID cycle(s) excluded - probe read wrong colours]"
            if not valid:
                print(
                    f"{report['framework']:>9}: NO VALID CYCLES - the window stopped "
                    f"painting; the zero is meaningless{note}",
                    file=sys.stderr,
                )
                continue
            print(
                f"{report['framework']:>9}: {report['window']['native_descendants']:>3} "
                f"native windows, {blanks}/{total} frames with a blanked sidebar{note}",
                file=sys.stderr,
            )
    return 0


def _print_report(report: dict) -> None:
    print(f"--- {report['framework']} ---", file=sys.stderr)
    if "error" in report:
        print(f"ERROR: {report['error']}", file=sys.stderr)
        return
    window = report["window"]
    print(
        f"window {window['class']} style={window['style']} exstyle={window['exstyle']} "
        f"rect={window['rect']} native_descendants={window['native_descendants']}",
        file=sys.stderr,
    )
    if "reference" not in report:
        # Debug run: the strip profile is the payload.
        return
    print(
        f"capture bbox={report['probe_bbox']} reference="
        f"sidebar {report['reference']['sidebar_mean']} "
        f"content {report['reference']['content_mean']} "
        f"(control passed on attempt {report['reference']['attempts']})",
        file=sys.stderr,
    )
    for cycle in report["cycles"]:
        flag = "" if cycle.get("probe_valid", True) else "  << INVALID PROBE"
        print(
            f"  cycle {cycle['cycle']}: {cycle['frames']} frames @ "
            f"{cycle['frame_interval_ms']} ms | sidebar settled "
            f"{cycle['sidebar_settled']} max {cycle['sidebar_max']} | "
            f"blank {cycle['sidebar_blank_frames']} {cycle['sidebar_blank_detail']} | "
            f"unpainted {cycle['unpainted_span_ms']} ms, "
            f"repainted by {cycle['resolved_at_ms']} ms | "
            f"content dark {cycle['content_dark_frames']}{flag}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
