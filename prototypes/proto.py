"""Multi-candidate window-lifecycle prototype.

Candidates
----------
a   : overrideredirect(True) forever + WS_EX_APPWINDOW + ShowWindow minimize
      (what the current app does, minus the overrideredirect toggling)
a2  : same as ``a`` but hide/show the window after applying WS_EX_APPWINDOW so
      the shell re-evaluates the taskbar button
b   : never use overrideredirect; keep the window a normal overlapped toplevel
      and strip WS_CAPTION/WS_THICKFRAME/... with SetWindowLongPtr
b2  : ``b`` plus a WM_NCCALCSIZE handler so the non-client area stays zero even
      if Tk re-adds WS_CAPTION after a state change

Each run measures, at every state:
  * non-client frame thickness (a visible native title bar => >0)
  * client size
  * WS_CAPTION presence
  * whether a taskbar button with the window title exists

Taskbar button detection is done by diffing the taskbar strip against a
post-destroy baseline, because the Windows 10 task list is owner-drawn and
exposes no child HWNDs.

Usage:
    python proto.py --mode b2
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tkinter as tk
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import grab  # noqa: E402
import winapi as W  # noqa: E402

WINDOW_WIDTH = 820
WINDOW_HEIGHT = 500
CYCLES = 5
WATCHDOG_MS = 120_000
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
TITLE = "ProtoWin"
TASKBAR_SCAN = (230, 1650)  # x range holding task buttons (excludes search + tray)


class Prototype(tk.Tk):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.title(TITLE)
        self.resizable(False, False)
        self.configure(bg="#f3f4f7")
        if mode in ("a", "a2", "e", "e2", "e3", "e4", "f", "g", "h", "i", "i2"):
            self.overrideredirect(True)

        self._root_hwnd = 0
        self._measurements: list[dict] = []
        self._cycle = 0
        self._finished = False
        self._taskbar_strips: dict[str, str] = {}
        self._nccalc_hits = 0
        self._taskbar_tab_added = None

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max((screen_w - WINDOW_WIDTH) // 2, 0)
        y = max((screen_h - WINDOW_HEIGHT) // 2 - 60, 0)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

        title_bar = tk.Frame(self, bg="#000000", height=38)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(
            title_bar,
            text="  Codex 配置助手  (prototype)",
            bg="#000000",
            fg="#ffffff",
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", fill="y")

        controls = tk.Frame(title_bar, bg="#000000")
        controls.pack(side="right", fill="y")
        tk.Button(
            controls,
            text="—",
            command=self._on_minimize,
            bg="#000000",
            fg="#ffffff",
            activebackground="#2b2b2b",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Microsoft YaHei UI", 12, "bold"),
            padx=14,
        ).pack(side="left", fill="y")

        body = tk.Frame(self, bg="#f3f4f7")
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=f"mode {mode} — minimize / restore probe",
            bg="#f3f4f7",
            fg="#20242b",
            font=("Microsoft YaHei UI", 11),
        ).pack(expand=True)

        self.after(400, self._setup_native)
        self.after(1400, self._run_cycle)
        self.after(WATCHDOG_MS, self._finish)

        if mode == "f":
            # Convert the wrapper before Tk first maps the window, so the shell
            # sees a normal overlapped window from its very first show.
            self._apply_overlapped_style()
            self.bind("<Map>", self._on_first_map, add="+")
        elif mode == "g":
            # Same idea as ``f`` but strictly once, before the first map, with no
            # later re-application (re-applying during Map disturbed Tk).
            self._apply_overlapped_style()

    def _apply_overlapped_style(self) -> None:
        hwnd = W.root_hwnd(self.winfo_id())
        if not hwnd:
            return
        self._root_hwnd = hwnd
        W.make_overlapped_without_caption(hwnd)
        W.apply_taskbar_appwindow(hwnd)

    def _on_first_map(self, _event=None) -> None:
        self.unbind("<Map>")
        self._apply_overlapped_style()

    # ------------------------------------------------------------------ setup
    def _setup_native(self) -> None:
        self._root_hwnd = W.root_hwnd(self.winfo_id())
        self._log(
            "hierarchy",
            {
                "winfo_id_class": W.class_name(self.winfo_id()),
                "root": f"0x{self._root_hwnd:X}",
                "root_class": W.class_name(self._root_hwnd),
                "owner": f"0x{W.as_hwnd(W.user32.GetWindow(W.wintypes.HWND(self._root_hwnd), 4)):X}",
            },
        )

        if self.mode in ("a", "a2"):
            W.apply_taskbar_appwindow(self._root_hwnd)
            if self.mode == "a2":
                W.user32.ShowWindow(self._root_hwnd, W.SW_HIDE)
                self.update()
                W.user32.ShowWindow(self._root_hwnd, W.SW_SHOW)
                W.apply_taskbar_appwindow(self._root_hwnd)
        elif self.mode in ("i", "i2"):
            # Honest popup window: Tk and Windows agree it is borderless.  The
            # taskbar button comes from the shell API instead of a hide/show hack.
            W.apply_taskbar_appwindow(self._root_hwnd)
            self._taskbar_tab_added = W.taskbar_add_tab(self._root_hwnd)
            if self.mode == "i2":
                W.force_taskbar_reevaluation(self._root_hwnd)
                self._taskbar_tab_added = W.taskbar_add_tab(self._root_hwnd) or self._taskbar_tab_added
        elif self.mode in ("e", "e2", "e3", "e4", "h"):
            W.make_overlapped_without_caption(self._root_hwnd)
            W.apply_taskbar_appwindow(self._root_hwnd)
            if self.mode == "h":
                self._taskbar_tab_added = W.taskbar_add_tab(self._root_hwnd)
            if self.mode == "e2":
                # The shell only re-evaluates taskbar eligibility when the window
                # is re-shown after its styles change.
                W.user32.ShowWindow(self._root_hwnd, W.SW_HIDE)
                self.update()
                W.user32.ShowWindow(self._root_hwnd, W.SW_SHOW)
                W.apply_taskbar_appwindow(self._root_hwnd)
                W.user32.SetForegroundWindow(self._root_hwnd)
            elif self.mode == "e3":
                W.force_taskbar_reevaluation(self._root_hwnd)
            elif self.mode == "e4":
                # Hide/show without letting Tk process the Unmap in between.
                W.user32.ShowWindow(self._root_hwnd, W.SW_HIDE)
                W.user32.ShowWindow(self._root_hwnd, W.SW_SHOW)
                W.apply_taskbar_appwindow(self._root_hwnd)
        elif self.mode in ("f", "g"):
            self._apply_overlapped_style()
        elif self.mode in ("b", "b2"):
            W.strip_decorations(self._root_hwnd)
            if self.mode == "b2":
                self._install_nccalc_handler(self._root_hwnd)

        self._log("after-setup", {"describe": W.describe(self._root_hwnd)})

    def _reassert_style(self) -> None:
        if not self._finished and self._root_hwnd:
            W.make_overlapped_without_caption(self._root_hwnd)

    def _install_nccalc_handler(self, hwnd: int) -> None:
        """Return 0 from WM_NCCALCSIZE so the client area covers the window."""
        user32 = W.user32
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = (
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.CallWindowProcW.restype = ctypes.c_ssize_t

        original = user32.GetWindowLongPtrW(hwnd, -4)
        if not original:
            return

        @wndproc_type
        def handler(window, message, wparam, lparam):
            if message == 0x0083 and wparam:  # WM_NCCALCSIZE with wParam TRUE
                self._nccalc_hits += 1
                return 0
            return user32.CallWindowProcW(original, window, message, wparam, lparam)

        W.user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(handler, ctypes.c_void_p))
        self._handler = handler  # keep alive

    # ------------------------------------------------------------- actions
    def _on_minimize(self) -> None:
        self._do_minimize()

    def _do_minimize(self) -> None:
        if self.mode in ("a", "a2", "e", "e2", "e3", "e4", "f", "g", "h", "i", "i2"):
            W.minimize_window(self._root_hwnd)
        else:
            self.iconify()

    def _do_restore(self) -> None:
        if self.mode in ("a", "a2", "e", "e2", "e3", "e4", "f", "g", "h", "i", "i2"):
            W.restore_window(self._root_hwnd)
        else:
            W.restore_window(self._root_hwnd)

    # ------------------------------------------------------------- harness
    def _snapshot(self, tag: str) -> dict:
        hwnd = self._root_hwnd
        frame = W.frame_thickness(hwnd)
        client = W.client_rect(hwnd)
        iconic = W.is_iconic(hwnd)
        record = {
            "tag": tag,
            "describe": W.describe(hwnd),
            "frame": list(frame),
            "client": list(client),
            "iconic": iconic,
            "visible": W.is_visible(hwnd),
            "style_caption": bool(W.get_style(hwnd) & W.WS_CAPTION),
            "style_popup": bool(W.get_style(hwnd) & W.WS_POPUP),
            "ex_appwindow": bool(W.get_ex_style(hwnd) & W.WS_EX_APPWINDOW),
            "has_native_frame": frame[1] > 0,
            "size_ok": list(client) == [WINDOW_WIDTH, WINDOW_HEIGHT],
            "tk_state": self.state(),
            "nccalc_hits": self._nccalc_hits,
        }
        try:
            strip_path = os.path.join(OUT_DIR, f"{self.mode}-{tag}-taskbar.png")
            strip = grab.grab_taskbar_strip()
            strip.save(strip_path)
            record["taskbar_screenshot"] = strip_path
            record["button_area_right_edge"] = grab.taskbar_button_area_right_edge(strip)
            self._taskbar_strips[tag] = strip_path
        except Exception as error:  # noqa: BLE001
            record["taskbar_screenshot_error"] = repr(error)

        if not iconic:
            try:
                path = os.path.join(OUT_DIR, f"{self.mode}-{tag}-win.png")
                grab.grab_window(hwnd, margin=40).save(path)
                record["window_screenshot"] = path
            except Exception as error:  # noqa: BLE001
                record["window_screenshot_error"] = repr(error)

        self._measurements.append(record)
        self._log("snapshot", record)
        return record

    def _run_cycle(self) -> None:
        if self._finished:
            return
        if self._cycle >= CYCLES:
            self._finish()
            return
        self._cycle += 1
        self._snapshot(f"cycle{self._cycle}-normal")
        self.update()
        self.after(250, self._step_minimize)

    def _step_minimize(self) -> None:
        if self._finished:
            return
        index = self._cycle
        self._do_minimize()
        self.after(900, lambda: self._after_minimize(index))

    def _after_minimize(self, index: int) -> None:
        if self._finished:
            return
        self._snapshot(f"cycle{index}-minimized")
        self.after(250, lambda: self._step_restore(index))

    def _step_restore(self, index: int) -> None:
        if self._finished:
            return
        self._do_restore()
        self.after(900, lambda: self._after_restore(index))

    def _after_restore(self, index: int) -> None:
        if self._finished:
            return
        self._snapshot(f"cycle{index}-restored")
        self.after(300, self._run_cycle)

    # ---------------------------------------------------------------- finish
    def _finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._log("final", {"describe": W.describe(self._root_hwnd)})

        # Capture a baseline with no window of ours alive, then diff.
        try:
            self.withdraw()
            self.update()
            self.after(600, self._finish_after_withdraw)
        except tk.TclError:
            self._write_report({})

    def _finish_after_withdraw(self) -> None:
        baseline_path = os.path.join(OUT_DIR, f"{self.mode}-baseline-taskbar.png")
        try:
            grab.grab_taskbar_strip().save(baseline_path)
        except Exception:  # noqa: BLE001
            baseline_path = None
        self.after(100, lambda: self._write_report({"baseline": baseline_path}))

    def _write_report(self, extra: dict) -> None:
        diffs = {}
        baseline_path = extra.get("baseline")
        baseline_edge = None
        if baseline_path and os.path.exists(baseline_path):
            from PIL import Image, ImageChops

            baseline = Image.open(baseline_path).convert("RGB")
            baseline_edge = grab.taskbar_button_area_right_edge(baseline)
            for tag, path in self._taskbar_strips.items():
                if not os.path.exists(path):
                    continue
                current = Image.open(path).convert("RGB")
                if current.size != baseline.size:
                    diffs[tag] = {"error": "size mismatch"}
                    continue
                region = (TASKBAR_SCAN[0], 0, TASKBAR_SCAN[1], baseline.height)
                box = ImageChops.difference(
                    current.crop(region), baseline.crop(region)
                ).convert("L")
                changed = sum(1 for value in box.getdata() if value > 24)
                edge = grab.taskbar_button_area_right_edge(current)
                diffs[tag] = {
                    "changed_pixels": changed,
                    "button_likely": changed > 2000,
                    "right_edge": edge,
                    "right_edge_delta": None if baseline_edge is None else edge - baseline_edge,
                    "button_present": baseline_edge is not None and (edge - baseline_edge) > 80,
                }

        report = {
            "mode": self.mode,
            "measurements": self._measurements,
            "baseline_right_edge": baseline_edge,
            "taskbar_diff_vs_baseline": diffs,
        }
        path = os.path.join(OUT_DIR, f"report-{self.mode}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print("REPORT " + path)
        print("SUMMARY " + json.dumps({"mode": self.mode, "taskbar": diffs}, ensure_ascii=False))
        self.quit()
        self.destroy()

    def _log(self, tag: str, payload: dict) -> None:
        print(f"[{tag}] " + json.dumps(payload, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="b2")
    args = parser.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    app = Prototype(args.mode)
    try:
        app.mainloop()
    except tk.TclError:
        pass


if __name__ == "__main__":
    main()
