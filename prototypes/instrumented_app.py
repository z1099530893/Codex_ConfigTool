"""Run the application from source, optionally with a trace or an experimental fix.

Why this exists
---------------
The restore flash is intermittent and the packaged build cannot be instrumented.
Every function that can touch the window style is wrapped so each call can be
timestamped and lined up against the frame timeline that ``verify_restore_flash.py``
records.  The same wrappers make it cheap to try candidate fixes **before** editing
the application: ``--variant`` patches the app in memory and the harness measures
the result.

Variants are composable with ``+``, so "tclguard+dwm-notransition" is valid.

``baseline``          the app as it ships
``silent``            ``_ensure_window_integrity`` returns immediately and does no I/O
                      (the control for "is the app's Map handler the cause?")
``filtered``          ignore ``<Map>`` events belonging to child widgets, checked in
                      Python
``nobind``            no ``<Map>`` binding at all - the upper bound of what removing
                      the handler's cost can buy
``tclguard``          guard on ``%W`` in Tcl so only the toplevel's own map reaches
                      Python
``strip-sysmenu``     remove WS_SYSMENU, to see whether the bits this project added
                      are what makes the restore flash
``strip-minbox``      remove WS_SYSMENU | WS_MINIMIZEBOX, i.e. the pre-change window
``overlapped``        clear WS_POPUP (``make_overlapped_without_caption``), so the
                      window is an undecorated overlapped window instead of a popup
``dwm-notransition``  ``DWMWA_TRANSITIONS_FORCEDISABLED``, which turns off the window's
                      minimize/restore animation
``composited``        add ``WS_EX_COMPOSITED`` so DWM double-buffers the window
``no-erase``          clear the window class background brush so Windows stops erasing
                      the client area before each repaint
``sync-redraw``       on a re-map, force the window *and every descendant* to repaint
                      synchronously (``RDW_ALLCHILDREN | RDW_UPDATENOW``) instead of
                      letting Windows spread the repaint across several passes of the
                      message loop - the mechanism the captured frames show
``sync-redraw-idle``  same, but scheduled with ``after_idle`` so it runs after Tk has
                      finished its own map handling rather than in the middle of it
``stamp``             no behaviour change; writes the absolute epoch of the first
                      ``<Map>`` callback of each restore burst to
                      ``out/restore-stamp.log`` so it can be subtracted from the
                      restore epoch the harness records
``no-erasebkgnd``     subclass the window procedure and return 1 from
                      ``WM_ERASEBKGND``, so an already-correct window is not erased
                      before it is repainted
``no-erasebkgnd-child`` the same no-op applied to the *child* that covers the
                      navigation strip instead of to the toplevel.  The message spy
                      counts one erase per restore on the toplevel but 120 on the
                      child, so this is the window the erase actually happens to
``lockupdate``        hold ``LockWindowUpdate`` across the whole re-map burst and
                      release it with one synchronous repaint, so the redraw Tk does
                      after the children are mapped never reaches the screen in
                      pieces
``layered``           add ``WS_EX_LAYERED`` and set a full alpha with
                      ``SetLayeredWindowAttributes``, so the window is redirected
                      through DWM instead of being painted straight to the screen.
                      This is the standard remedy for erase-before-paint tearing in
                      borderless windows and it is a *different* redirection from
                      ``WS_EX_COMPOSITED``, so it has to be measured separately
``msgspy``            no behaviour change; subclasses the window procedure of the
                      toplevel *and* of the child that covers the sidebar, logging
                      their messages with an absolute epoch so a blank frame can be
                      attributed to a message rather than guessed at

Tracing costs a file write per call, which is far from free at 100+ calls per
restore, so nothing is written unless ``CODEX_TRACE=1``.  Comparing a traced run
against an untraced one would otherwise measure the tracer rather than the variant.

Usage (driven by the harness, not by hand):
    python instrumented_app.py [--variant V] [--trace PATH]
"""

from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import codex_config_tool as app  # noqa: E402

TRACE_DEFAULT = os.path.join(HERE, "out", "window-trace.log")
FEATURES = (
    "baseline",
    "silent",
    "filtered",
    "nobind",
    "tclguard",
    "strip-sysmenu",
    "strip-minbox",
    "overlapped",
    "dwm-notransition",
    "composited",
    "no-erase",
    "sync-redraw",
    "sync-redraw-idle",
    "stamp",
    "no-erasebkgnd",
    "no-erasebkgnd-child",
    "lockupdate",
    "msgspy",
    "layered",
    "idlecount",
)

WS_EX_COMPOSITED = 0x02000000
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002
DWMWA_TRANSITIONS_FORCEDISABLED = 3
GCLP_HBRBACKGROUND = -10
SWP_FRAME_ONLY = 0x0027
# The navigation strip, measured from the window's own left edge.  Measured, not
# assumed: ``diag_child_windows.py`` and the census in ``msgspy`` both report the
# sidebar container as a 142px-wide child, so a 240px strip would also cover the
# left edge of the content area.
SIDEBAR_WIDTH = 142


class Trace:
    """Timestamped call log; counts every call, writes only when ``verbose``."""

    def __init__(self, path: str, verbose: bool) -> None:
        self.verbose = verbose
        self.counts: dict[str, int] = {}
        self.start = time.time()
        if verbose:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.handle = open(path, "w", encoding="utf-8", buffering=1)
        else:
            self.handle = None
        self.write("=== trace start ===")

    def write(self, message: str) -> None:
        if self.handle is not None:
            now = time.time()
            # Absolute epoch *and* elapsed.  The harness records the epoch of the
            # restore call from another process, and both processes share the
            # machine clock, so the two timelines can only be subtracted if this
            # one carries an absolute stamp - a relative-only log cannot be aligned
            # with anything.
            self.handle.write(
                f"{now:.6f} {(now - self.start) * 1000:9.1f}ms {message}\n"
            )

    def wrap(self, owner, name: str, describe=None) -> None:
        original = getattr(owner, name)

        def traced(*args, **kwargs):
            self.counts[name] = self.counts.get(name, 0) + 1
            if self.verbose:
                detail = describe(*args, **kwargs) if describe else ""
                self.write(f"{name} {detail}".rstrip())
            return original(*args, **kwargs)

        traced.__name__ = name
        setattr(owner, name, traced)

    def summary(self) -> str:
        parts = ", ".join(f"{name}={count}" for name, count in sorted(self.counts.items()))
        return parts or "(no calls)"


def build_features(features: set[str], cls, trace: Trace) -> dict:
    """Patch ``cls`` / the app module in memory for the requested features."""
    state: dict[str, int] = {}

    # ---------------------------------------------------------------- window bits
    if features & {"composited", "dwm-notransition", "no-erase"}:
        register_before_extras = app.register_appwindow_with_shell
        applied: set[int] = set()

        def register_extras(hwnd, user32=None):
            register_before_extras(hwnd, user32)
            if not hwnd or hwnd in applied:
                return
            applied.add(hwnd)
            import ctypes

            user32 = user32 or ctypes.windll.user32
            if "composited" in features:
                style = user32.GetWindowLongW(hwnd, -20) | WS_EX_COMPOSITED
                user32.SetWindowLongW(hwnd, -20, style)
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAME_ONLY)
                trace.write(f"WS_EX_COMPOSITED applied -> {style:#010x}")
            if "dwm-notransition" in features:
                # "Disables the window's transitions" - the minimize/restore
                # animation.  With the animation on, DWM shows the preserved
                # snapshot first (which looks perfect) and only hands over to the
                # live window at the end, so a window still repainting shows up as
                # "correct, blank, correct" - exactly the reported flash.
                dwmapi = ctypes.WinDLL("dwmapi")
                value = ctypes.c_int(1)
                result = dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_uint(DWMWA_TRANSITIONS_FORCEDISABLED),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                trace.write(f"DWMWA_TRANSITIONS_FORCEDISABLED -> hr={result:#x}")
            if "no-erase" in features:
                user32.SetClassLongPtrW.argtypes = (
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.c_void_p,
                )
                previous = user32.SetClassLongPtrW(hwnd, GCLP_HBRBACKGROUND, 0)
                trace.write(f"class background brush cleared (was {previous:#x})")

        app.register_appwindow_with_shell = register_extras

    if "layered" in features:
        # A layered window is redirected: DWM composites it from a surface the app
        # paints into, so the "erase to background, then repaint children" sequence
        # never reaches the screen as two separate visible states.  This is the
        # classic remedy for exactly the artefact measured here, and it is a
        # different mechanism from WS_EX_COMPOSITED (which double-buffers the
        # window's own painting) - so it needs its own measurement.
        import ctypes

        register_before_layered = app.register_appwindow_with_shell
        layered_applied: set[int] = set()

        def register_layered(hwnd, user32=None):
            register_before_layered(hwnd, user32)
            if not hwnd or hwnd in layered_applied:
                return
            layered_applied.add(hwnd)
            user32 = user32 or ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, -20) | WS_EX_LAYERED
            user32.SetWindowLongW(hwnd, -20, style)
            # Alpha 254/255 rather than 255: at a full 255 some drivers drop the
            # window back to the non-layered path, and the redirection is the whole
            # point of the variant.  One step below full is invisible.
            ok = user32.SetLayeredWindowAttributes(
                ctypes.c_void_p(hwnd), ctypes.c_uint(0), ctypes.c_ubyte(254), LWA_ALPHA
            )
            trace.write(
                f"WS_EX_LAYERED applied -> {style:#010x} "
                f"SetLayeredWindowAttributes -> {ok}"
            )

        app.register_appwindow_with_shell = register_layered

    # ------------------------------------------------------------- Map handling
    if "overlapped" in features:
        # ``overrideredirect(True)`` makes Tk set WS_POPUP.  An earlier build of
        # this app did not have WS_POPUP (its style was 0x160A0008, the current one
        # is 0x960A0008), and Windows restores a popup differently from an
        # overlapped window - so this is the last structural difference between the
        # two builds worth testing.
        import winapi as W

        register_before_overlapped = app.register_appwindow_with_shell
        done: set[int] = set()

        def register_overlapped(hwnd, user32=None):
            register_before_overlapped(hwnd, user32)
            if not hwnd or hwnd in done:
                return
            done.add(hwnd)
            trace.write(f"before overlapped: {W.describe(hwnd)}")
            W.make_overlapped_without_caption(hwnd)
            trace.write(f"after overlapped: {W.describe(hwnd)}")

        app.register_appwindow_with_shell = register_overlapped

    if features & {"strip-minbox", "strip-sysmenu"}:
        # Undo the bits this project added, to find out whether *they* are what
        # makes the restore flash.  strip-sysmenu drops WS_SYSMENU only;
        # strip-minbox drops both, i.e. the window exactly as it was before.
        strip = 0
        if "strip-sysmenu" in features:
            strip |= 0x00080000  # WS_SYSMENU
        if "strip-minbox" in features:
            strip |= 0x00080000 | 0x00020000  # WS_SYSMENU | WS_MINIMIZEBOX

        def stripped_minimizable(hwnd, user32=None) -> bool:
            if not hwnd:
                return False
            import ctypes

            user32 = user32 or ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, -16)
            if style & strip:
                user32.SetWindowLongW(hwnd, -16, style & ~strip)
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAME_ONLY)
            return bool(user32.GetWindowLongW(hwnd, -16) & 0x00020000)

        app.make_window_minimizable = stripped_minimizable

    if features & {"sync-redraw", "sync-redraw-idle"}:
        # The captured frames show the tear is *progressive*: on restore the child
        # windows paint one after another across several passes of the message
        # loop, and the not-yet-painted ones still hold pixels from whatever was
        # behind the window.  ``RDW_ALLCHILDREN | RDW_UPDATENOW`` collapses that
        # into one synchronous pass.  A re-map fires ``<Map>`` once per descendant,
        # so this is throttled - otherwise it would do ~114 full repaints.
        import winapi as W

        original_integrity = cls._ensure_window_integrity
        last: dict[str, float] = {"at": 0.0, "calls": 0, "skipped": 0}

        def integrity_with_redraw(self, event=None):
            result = original_integrity(self, event)
            now = time.time()
            if now - last["at"] < 0.08:
                last["skipped"] += 1
                return result
            last["at"] = now
            last["calls"] += 1
            hwnd = self._window_handle()
            if not hwnd:
                return result
            trace.write(f"sync_redraw_all #{last['calls']} hwnd={hwnd:#x}")
            if "sync-redraw-idle" in features:
                self.after_idle(lambda h=hwnd: W.sync_redraw_all(h))
            else:
                ok = W.sync_redraw_all(hwnd)
                trace.write(f"sync_redraw_all #{last['calls']} -> {ok}")
            return result

        cls._ensure_window_integrity = integrity_with_redraw

    if "no-erasebkgnd" in features:
        # The frame timeline is *correct -> uniform background -> correct*, so
        # something erases an already-correct window and then repaints it.  This
        # subclasses the window procedure and turns WM_ERASEBKGND into a no-op so
        # the old (correct) pixels survive until the real paint lands.
        import winapi as W

        register_before_no_erasebkgnd = app.register_appwindow_with_shell
        subclassed: set[int] = set()

        def register_no_erase(hwnd, user32=None):
            register_before_no_erasebkgnd(hwnd, user32)
            if not hwnd or hwnd in subclassed:
                return
            subclassed.add(hwnd)
            ok = W.suppress_background_erase(hwnd)
            trace.write(f"suppress_background_erase({hwnd:#x}) -> {ok}")
            trace.write(f"  state after install: {W.erase_subclass_state(hwnd)}")

        app.register_appwindow_with_shell = register_no_erase

        # Installing the subclass is not the same as it being live: Tk can reset
        # GWLP_WNDPROC afterwards and drop it, which would make "suppressing the
        # erase changes nothing" a statement about nothing.  Log the state on the
        # way through each re-map so a run can prove the subclass survived and
        # that erase messages were actually swallowed.
        original_integrity = cls._ensure_window_integrity
        seen = {"n": 0}

        def integrity_with_erase_state(self, event=None):
            result = original_integrity(self, event)
            seen["n"] += 1
            if seen["n"] % 20 == 1:
                hwnd = self._window_handle()
                if hwnd:
                    trace.write(
                        f"erase state after map #{seen['n']}: "
                        f"{W.erase_subclass_state(hwnd)}"
                    )
            return result

        cls._ensure_window_integrity = integrity_with_erase_state

    if "no-erasebkgnd-child" in features:
        # The previous variant suppressed WM_ERASEBKGND on the *toplevel*, and the
        # message spy shows why that could never matter: the toplevel receives one
        # erase per restore, while the TkChild covering the sidebar receives
        # **120**.  Suppressing the wrong window's erase is a measurement of
        # nothing, so this applies the same no-op to the child that actually owns
        # the pixels the probe watches.
        import winapi as W

        register_before_child_erase = app.register_appwindow_with_shell
        subclassed: set[int] = set()

        def pick_child_over_probe(hwnd):
            """The descendant that actually owns the probe's pixels.

            Full-window children are excluded.  The message spy counts one erase
            per restore on the wrapper that spans the whole client area, but 120 on
            the container below it - so "the child with the largest strip overlap"
            picks the wrapper, and suppressing *its* erase is another measurement
            of a window that is barely erased.
            """
            root_left, root_top, root_w, root_h = W.window_rect(hwnd)
            best, best_area, census = None, 0, []
            for child in W.child_windows(hwnd):
                left, top, width, height = W.window_rect(child)
                rel_left = left - root_left
                overlap = max(
                    0, min(rel_left + width, SIDEBAR_WIDTH) - max(rel_left, 0)
                )
                area = overlap * height
                full = width >= root_w and height >= root_h
                census.append(
                    f"{child:#x} {W.class_name(child)!r} "
                    f"rel({rel_left},{top - root_top},{width}x{height}) "
                    f"strip={area}{' FULL' if full else ''}"
                )
                if not full and area > best_area:
                    best, best_area = child, area
            trace.write("  pick census: " + " | ".join(census))
            return best, best_area

        def register_no_erase_child(hwnd, user32=None):
            register_before_child_erase(hwnd, user32)
            if not hwnd or hwnd in subclassed:
                return
            subclassed.add(hwnd)
            child, area = pick_child_over_probe(hwnd)
            if child is None:
                trace.write("no-erasebkgnd-child: no child covers the strip")
                return
            ok = W.suppress_background_erase(child)
            trace.write(
                f"suppress_background_erase(child {child:#x}, strip area {area}px2) "
                f"-> {ok}"
            )
            trace.write(f"  state after install: {W.erase_subclass_state(child)}")

        app.register_appwindow_with_shell = register_no_erase_child

        # Same caveat as above: installing the subclass is not the same as it
        # being live, and the child is re-created far more often than the toplevel.
        original_integrity = cls._ensure_window_integrity
        child_seen = {"n": 0}

        def integrity_with_child_erase_state(self, event=None):
            result = original_integrity(self, event)
            child_seen["n"] += 1
            if child_seen["n"] % 20 == 1:
                hwnd = self._window_handle()
                if hwnd:
                    child, _ = pick_child_over_probe(hwnd)
                    if child is not None:
                        trace.write(
                            f"child erase state after map #{child_seen['n']}: "
                            f"{W.erase_subclass_state(child)}"
                        )
            return result

        cls._ensure_window_integrity = integrity_with_child_erase_state

    if "lockupdate" in features:
        # The blank frame lands at ~64 ms, right after the ~114-event <Map> burst
        # ends (~57-62 ms), so the tear is the full redraw Tk does once the
        # children are mapped.  Freeze painting for the whole burst and release it
        # with a single synchronous repaint, so no intermediate state is ever
        # presented.  Only armed after a real minimize, so the startup map burst
        # still paints normally.
        import winapi as W

        armed = {"minimized": False}

        original_minimize = cls._minimize_window

        def minimize_tracked(self):
            armed["minimized"] = True
            return original_minimize(self)

        cls._minimize_window = minimize_tracked

        original_integrity = cls._ensure_window_integrity
        burst = {"last": 0.0, "locked": False}

        def integrity_locked(self, event=None):
            result = original_integrity(self, event)
            now = time.time()
            starting = now - burst["last"] > 0.5
            burst["last"] = now
            if starting and armed["minimized"] and not burst["locked"]:
                hwnd = self._window_handle()
                if hwnd and W.lock_window_update(hwnd):
                    burst["locked"] = True
                    trace.write(f"lockupdate ON {hwnd:#x}")

                    def release(h=hwnd):
                        burst["locked"] = False
                        ok = W.unlock_and_repaint(h)
                        trace.write(f"lockupdate OFF + repaint -> {ok}")

                    self.after(70, release)
            return result

        cls._ensure_window_integrity = integrity_locked

    if "stamp" in features:
        # Answers the question that decides whether *any* Python-side fix can
        # work: how long after the restore does the app first get control?
        # ``verify_restore_flash.py`` records the absolute epoch of the restore
        # call in each run, and this writes the absolute epoch of the first
        # ``<Map>`` callback of each restore burst, so the two can be subtracted
        # on the same machine clock.  If that offset is larger than the flash
        # window, no amount of Python can prevent it.
        stamp_path = os.path.join(HERE, "out", "restore-stamp.log")
        os.makedirs(os.path.dirname(stamp_path), exist_ok=True)
        burst = {"last": 0.0, "first": 0.0, "count": 0, "summary_scheduled": False}

        def write_stamp(line: str) -> None:
            with open(stamp_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        def burst_summary():
            burst["summary_scheduled"] = False
            if burst["count"]:
                write_stamp(
                    f"{burst['last']:.6f} burst_end count={burst['count']}"
                )

        original_integrity = cls._ensure_window_integrity

        def integrity_with_stamp(self, event=None):
            now = time.time()
            if now - burst["last"] > 0.5:
                burst["first"] = now
                burst["count"] = 0
            burst["last"] = now
            burst["count"] += 1
            if burst["count"] == 1:
                write_stamp(f"{now:.6f} first_map")
            if not burst["summary_scheduled"]:
                burst["summary_scheduled"] = True
                self.after(600, burst_summary)
            return original_integrity(self, event)

        cls._ensure_window_integrity = integrity_with_stamp

    if "silent" in features:

        def silent_integrity(self, _event=None):
            return None

        cls._ensure_window_integrity = silent_integrity

    if "filtered" in features:
        original_integrity = cls._ensure_window_integrity

        def filtered_integrity(self, event=None):
            widget = getattr(event, "widget", None)
            if event is not None and widget is not None and str(widget) != str(self):
                state["child_map_events"] = state.get("child_map_events", 0) + 1
                return None
            return original_integrity(self, event)

        cls._ensure_window_integrity = filtered_integrity

    if features & {"nobind", "tclguard"}:
        # ``silent`` and ``filtered`` still pay for 100+ Python callbacks per
        # restore.  These two remove that cost entirely so the residual flash can
        # be attributed either to the callbacks or to Tk's own repaint.
        original_bind = cls.bind

        def bind_with_guard(self, sequence=None, func=None, add=None):
            if sequence == "<Map>":
                if "nobind" in features:
                    return None
                command = self.register(func)
                self.tk.call(
                    "bind",
                    self._w,
                    "<Map>",
                    'if {"%W" eq "' + self._w + '"} {' + command + "}",
                )
                return None
            return original_bind(self, sequence, func, add)

        cls.bind = bind_with_guard

        original_integrity = cls._ensure_window_integrity

        def counted_integrity(self, event=None):
            state["toplevel_map_events"] = state.get("toplevel_map_events", 0) + 1
            return original_integrity(self, event)

        cls._ensure_window_integrity = counted_integrity

    if "idlecount" in features:
        import threading

        import winapi as W

        # The message spy has to run **in this process**.  ``GetWindowLongPtrW`` with
        # ``GWLP_WNDPROC`` returns 0 for a window owned by another process, so a
        # harness-side spy installs nothing at all - `diag_idle_paint.py` reported
        # "spy installed on 0/120" for exactly this reason, and an empty count is
        # indistinguishable from "no messages arrived" unless you check the install.
        # This variant is the in-process version, and it is the only way to answer
        # "is the app repainting while it just sits there?".
        idle_path = os.path.join(HERE, "out", "idle-messages.log")
        os.makedirs(os.path.dirname(idle_path), exist_ok=True)
        idle_handle = open(idle_path, "w", encoding="utf-8", buffering=1)
        idle_handle.write("# elapsed_ms busy_targets counts\n")
        idle_started = time.time()
        register_before_idlecount = app.register_appwindow_with_shell
        armed = {"done": False}

        def register_with_idlecount(hwnd, user32=None):
            register_before_idlecount(hwnd, user32)
            if not hwnd or armed["done"]:
                return
            armed["done"] = True
            targets = [("toplevel", hwnd)]
            for index, child in enumerate(W.child_windows(hwnd)):
                targets.append((f"child{index}", child))
            # Record what each index actually *is*, so a repainting child can be
            # attributed to a widget instead of a number.  Without this the log says
            # "child93 paints 354 times" and there is nothing to act on.
            root_left, root_top, _root_w, _root_h = W.window_rect(hwnd)
            for name, target in targets:
                left, top, width, height = W.window_rect(target)
                idle_handle.write(
                    f"# target {name} {target:#x} {W.class_name(target)!r} "
                    f"rel({left - root_left},{top - root_top},{width}x{height})\n"
                )
            installed = sum(1 for _name, target in targets if W.spy_window_messages(target, None))
            trace.write(f"idlecount: spy installed on {installed}/{len(targets)} window(s)")
            previous = {name: W.spy_message_counts(target) for name, target in targets}

            def report_loop():
                # A plain thread, not ``after``: the point is to observe the app while
                # *nothing* of ours touches its event loop.  Dict reads under the GIL
                # are safe against the window procedure's writes.
                last = previous
                while True:
                    time.sleep(1.0)
                    current = {name: W.spy_message_counts(t) for name, t in targets}
                    busy = {}
                    for name, counts in current.items():
                        delta = {
                            key: value - last.get(name, {}).get(key, 0)
                            for key, value in counts.items()
                            if value - last.get(name, {}).get(key, 0)
                        }
                        if delta:
                            busy[name] = delta
                    last = current
                    idle_handle.write(
                        f"{(time.time() - idle_started) * 1000:.0f} "
                        f"{busy if busy else 'none'}\n"
                    )

            threading.Thread(target=report_loop, daemon=True).start()

        app.register_appwindow_with_shell = register_with_idlecount

    if "msgspy" in features:
        import traceback

        import winapi as W

        spy_path = os.path.join(HERE, "out", "message-spy.log")
        register_before_msgspy = app.register_appwindow_with_shell
        spied: set[int] = set()

        def register_with_spy(hwnd, user32=None):
            register_before_msgspy(hwnd, user32)
            if not hwnd or hwnd in spied:
                return
            spied.add(hwnd)
            # Tk swallows exceptions raised inside a callback
            # (``report_callback_exception`` prints to stderr and carries on), so an
            # earlier version of this variant failed *silently*: the child spy line
            # simply never appeared in the trace and there was nothing to say why.
            # Everything below is therefore inside a try, and the failure is written
            # to the trace as well as stderr.
            try:
                ok = W.spy_window_messages(hwnd, spy_path)
                trace.write(f"spy_window_messages({hwnd:#x}) -> {ok}")
                trace.write(
                    f"  toplevel {W.describe(hwnd)}"
                )
                # The toplevel's message stream is identical whether or not the
                # window flashes, so the difference has to be in a child.  Spy on
                # the child covering the sidebar: if it receives WM_SHOWWINDOW(0)
                # and then (1), the toolkit is hiding and re-showing it, and its
                # area will show the parent's background in between - which no
                # amount of repainting the parent can prevent.
                #
                # ``window_rect`` returns *screen* coordinates and
                # ``(left, top, WIDTH, HEIGHT)``, not ``(left, top, right, bottom)``.
                # An earlier version of this variant compared screen x against the
                # window-relative strip 0..240, so for a window at screen x=550 every
                # overlap came out negative, every area read 0, the selection was
                # empty, and the child spy was never installed - silently, because
                # the trace line was inside the ``if best:`` that never ran.
                root_left, root_top, root_w, root_h = W.window_rect(hwnd)
                children = W.child_windows(hwnd)
                trace.write(
                    f"  child census: {len(children)} descendant window(s); "
                    f"toplevel at screen ({root_left},{root_top}) {root_w}x{root_h}"
                )
                wrapper, wrapper_area = None, 0
                sidebar, sidebar_area, census = None, 0, []
                for child in children:
                    left, top, width, height = W.window_rect(child)
                    rel_left, rel_top = left - root_left, top - root_top
                    # Window-relative overlap with the navigation strip.
                    overlap = max(0, min(rel_left + width, SIDEBAR_WIDTH) - max(rel_left, 0))
                    area = overlap * height
                    full = width >= root_w and height >= root_h
                    census.append(
                        f"{child:#x} {W.class_name(child)!r} "
                        f"rel({rel_left},{rel_top},{width}x{height}) strip={area}"
                    )
                    if full and width * height > wrapper_area:
                        wrapper, wrapper_area = child, width * height
                    if not full and area > sidebar_area:
                        sidebar, sidebar_area = child, area
                trace.write("  census detail: " + " | ".join(census))
                # The wrapper spans the whole client area and is therefore the child
                # that paints the background the blank frame shows, if any child
                # does.  The sidebar is the one the probe patch sits on.
                targets = []
                if wrapper is not None:
                    targets.append(("wrapper", wrapper, wrapper_area))
                if sidebar is not None:
                    targets.append(("sidebar", sidebar, sidebar_area))
                if not targets:
                    trace.write(
                        "  no child spans the client area and none overlaps the "
                        f"left {SIDEBAR_WIDTH}px strip - nothing to spy on"
                    )
                for label, target, area in targets:
                    child_path = os.path.join(
                        HERE, "out", f"message-spy-{label}.log"
                    )
                    child_ok = W.spy_window_messages(target, child_path)
                    trace.write(
                        f"spy_window_messages({label} {target:#x}, area {area}px2) "
                        f"-> {child_ok} [{child_path}]"
                    )
                    trace.write(f"  {label} {W.describe(target)}")
            except Exception:
                trace.write("  msgspy FAILED: " + traceback.format_exc().replace("\n", " | "))
                sys.stderr.write(traceback.format_exc())

        app.register_appwindow_with_shell = register_with_spy
        trace.write(f"msgspy -> {spy_path} plus one log per child target")

    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", default=TRACE_DEFAULT)
    parser.add_argument(
        "--variant",
        default=os.environ.get("CODEX_VARIANT", "baseline"),
        help="'+'-joined feature names; also settable with CODEX_VARIANT",
    )
    args = parser.parse_args()

    features = {part.strip() for part in args.variant.split("+") if part.strip()}
    unknown = features - set(FEATURES)
    if unknown:
        parser.error(f"unknown variant feature(s): {sorted(unknown)}")

    trace = Trace(args.trace, verbose=os.environ.get("CODEX_TRACE") == "1")

    def hwnd_detail(hwnd, *_rest, **_kw):
        return f"hwnd={hwnd:#x}" if hwnd else "hwnd=0"

    def attempt_detail(self, attempt=0, *_rest, **_kw):
        return f"attempt={attempt}"

    def integrity_detail(self, _event=None):
        try:
            ready = self._taskbar_button_ready
        except Exception:  # noqa: BLE001
            ready = "?"
        return f"taskbar_button_ready={ready}"

    # Module-level helpers: patching the module attribute is enough, because the
    # class methods look them up as globals at call time.
    trace.wrap(app, "register_appwindow_with_shell", hwnd_detail)
    trace.wrap(app, "make_window_minimizable", hwnd_detail)
    trace.wrap(app, "ensure_taskbar_button", hwnd_detail)

    cls = app.CodexConfigApp
    trace.wrap(cls, "_set_appwindow_style", attempt_detail)
    trace.wrap(cls, "_ensure_window_integrity", integrity_detail)
    trace.wrap(cls, "_minimize_window")

    state = build_features(features, cls, trace)
    trace.write(f"features: {sorted(features) or ['baseline']}")
    trace.write(f"=== variant {args.variant}: calling main() ===")
    try:
        app.main()
    finally:
        trace.write(
            f"=== main() returned; {trace.summary()}; extra={state} ==="
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
