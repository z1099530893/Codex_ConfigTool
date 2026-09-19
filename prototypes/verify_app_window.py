"""End-to-end validation of the *real* application's window lifecycle.

Instantiates ``CodexConfigApp`` from the project source (not a prototype),
disables the onboarding/update dialogs, then drives the actual custom minimize
button and a taskbar-style restore through five cycles while measuring:

  * non-client frame thickness  (a visible native title bar => > 0)
  * client size                 (must stay 820x500)
  * whether the window is iconic
  * whether the taskbar button exists (visual sheet + pixel diff)

Usage:
    python verify_app_window.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import grab  # noqa: E402
import winapi as W  # noqa: E402

import codex_config_tool as app_module  # noqa: E402

CYCLES = 5
OUT_DIR = os.path.join(HERE, "out")
WINDOW_WIDTH = app_module.WINDOW_WIDTH
WINDOW_HEIGHT = app_module.WINDOW_HEIGHT


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    # Keep the run headless-ish: no modal dialogs, no network, no disk scanning.
    app_module.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    app_module.CodexConfigApp.check_for_updates_on_startup = lambda self: None
    app_module.CodexConfigApp._load_initial_path = lambda self: None

    app = app_module.CodexConfigApp()
    records: list[dict] = []
    strips: dict[str, str] = {}
    state = {"cycle": 0, "hwnd": 0, "finished": False}

    def snapshot(tag: str) -> None:
        hwnd = state["hwnd"]
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
            "has_caption": bool(W.get_style(hwnd) & W.WS_CAPTION),
            "has_native_frame": frame[1] > 0,
            "size_ok": list(client) == [WINDOW_WIDTH, WINDOW_HEIGHT],
            "tk_state": app.state(),
        }
        try:
            path = os.path.join(OUT_DIR, f"app-{tag}-taskbar.png")
            grab.grab_taskbar_strip().save(path)
            strips[tag] = path
            record["taskbar_screenshot"] = path
        except Exception as error:  # noqa: BLE001
            record["taskbar_error"] = repr(error)
        if not iconic:
            try:
                path = os.path.join(OUT_DIR, f"app-{tag}-win.png")
                grab.grab_window(hwnd, margin=40).save(path)
                record["window_screenshot"] = path
            except Exception as error:  # noqa: BLE001
                record["window_error"] = repr(error)
        records.append(record)
        print("[snapshot] " + json.dumps(record, ensure_ascii=False))

    def setup() -> None:
        state["hwnd"] = app._window_handle()
        print("[setup] " + W.describe(state["hwnd"]))

    def start_cycle() -> None:
        if state["finished"]:
            return
        if state["cycle"] >= CYCLES:
            finish()
            return
        state["cycle"] += 1
        snapshot(f"cycle{state['cycle']}-normal")
        app.update()
        app.after(250, do_minimize)

    def do_minimize() -> None:
        # Exactly what the custom title-bar minimize button runs.
        app._minimize_window()
        app.after(900, after_minimize)

    def after_minimize() -> None:
        snapshot(f"cycle{state['cycle']}-minimized")
        app.after(250, do_restore)

    def do_restore() -> None:
        # What the shell does when the taskbar button is clicked.
        W.restore_window(state["hwnd"])
        app.after(900, after_restore)

    def after_restore() -> None:
        snapshot(f"cycle{state['cycle']}-restored")
        app.after(300, start_cycle)

    def finish() -> None:
        state["finished"] = True
        try:
            app.withdraw()
            app.update()
        except Exception:  # noqa: BLE001
            pass
        app.after(600, write_report)

    def write_report() -> None:
        baseline_path = os.path.join(OUT_DIR, "app-baseline-taskbar.png")
        baseline_edge = None
        diffs: dict[str, dict] = {}
        try:
            grab.grab_taskbar_strip().save(baseline_path)
            from PIL import Image, ImageChops

            baseline = Image.open(baseline_path).convert("RGB")
            baseline_edge = grab.taskbar_button_area_right_edge(baseline)
            for tag, path in strips.items():
                current = Image.open(path).convert("RGB")
                if current.size != baseline.size:
                    continue
                region = (900, 0, 1660, baseline.height)
                box = ImageChops.difference(
                    current.crop(region), baseline.crop(region)
                ).convert("L")
                changed = sum(1 for value in box.getdata() if value > 24)
                diffs[tag] = {"changed_pixels": changed}
        except Exception as error:  # noqa: BLE001
            diffs["error"] = {"message": repr(error)}

        report = {
            "window": [WINDOW_WIDTH, WINDOW_HEIGHT],
            "records": records,
            "baseline_right_edge": baseline_edge,
            "diffs": diffs,
        }
        path = os.path.join(OUT_DIR, "app-window-report.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)

        bad_size = [r["tag"] for r in records if not r["iconic"] and not r["size_ok"]]
        bad_frame = [r["tag"] for r in records if r["has_native_frame"] and not r["iconic"]]
        print("REPORT " + path)
        print(
            "SUMMARY "
            + json.dumps(
                {
                    "wrong_size_states": bad_size,
                    "native_frame_states": bad_frame,
                    "cycles": state["cycle"],
                },
                ensure_ascii=False,
            )
        )
        app.quit()
        app.destroy()

    app.after(700, setup)
    app.after(1300, start_cycle)
    app.after(120_000, finish)
    try:
        app.mainloop()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
