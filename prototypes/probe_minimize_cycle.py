"""Is the window really back after a restore?  Measure the cycle step by step.

``verify_qt_app.py``'s "no second title bar" check reads the mean luminance of
the window's top 38 px, expecting the custom black title bar.  Two runs in a row
returned a constant bright value (229, then 201) for every cycle, which is not
what a title bar looks like.  A screen capture of a window that is *still
minimised* reads whatever is behind it - so before treating that as a UI bug,
this probe measures the window state at each step of the cycle.

Reports, per cycle and per step: ``IsIconic``, ``IsWindowVisible``, the window
rect, the client rect, and the luminance of the top 38 px of a real capture.

Usage:
    python probe_minimize_cycle.py [--cycles 5]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import sandbox_env  # noqa: E402

SANDBOX, CONFIG_DIR = sandbox_env.isolate("codex-min-cycle-")

import grab  # noqa: E402
import winapi as W  # noqa: E402

import codex_config_tool as core  # noqa: E402

OUT_DIR = os.path.join(HERE, "out")
TITLE_HEIGHT = 38


def seed() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    core.write_text(
        CONFIG_DIR / "config.toml",
        core.build_fresh_config_toml("sk-probe", core.DEFAULT_PROVIDER, core.DEFAULT_BASE_URL),
    )
    core.update_auth_json(CONFIG_DIR / "auth.json", "sk-probe")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=5)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    seed()

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    import codex_config_qt as view

    view.CodexConfigWindow.show_onboarding_dialog = lambda self, force=False: None
    view.CodexConfigWindow.check_for_updates_on_startup = lambda self: None
    view.CodexConfigWindow._load_initial_path = lambda self: None

    app = view.create_application()
    window = view.CodexConfigWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    report: dict = {"cycles": []}

    def sample(hwnd: int, tag: str) -> dict:
        image = grab.grab_window(hwnd)
        band = image.crop((0, 0, image.width, TITLE_HEIGHT)).convert("L")
        data = list(band.getdata())
        entry = {
            "tag": tag,
            "iconic": W.is_iconic(hwnd),
            "visible": W.is_visible(hwnd),
            "window_rect": list(W.window_rect(hwnd)),
            "client": list(W.client_rect(hwnd)),
            "frame": list(W.frame_thickness(hwnd)),
            "title_band_mean": round(sum(data) / max(len(data), 1), 2),
            "qt_state": str(window.windowState()),
        }
        print("[step] " + json.dumps(entry, ensure_ascii=False), flush=True)
        return entry

    def run() -> None:
        hwnd = int(window.winId())
        report["hwnd"] = hex(hwnd)
        report["foreground"] = W.foreground_hwnd() == hwnd
        W.make_foreground(hwnd)
        time.sleep(0.6)
        report["cycles"].append({"cycle": 0, "steps": [sample(hwnd, "initial")]})

        for cycle in range(1, args.cycles + 1):
            steps = []
            window._minimize_window()
            time.sleep(0.85)
            steps.append(sample(hwnd, f"c{cycle}-minimized"))
            W.restore_window(hwnd)
            time.sleep(0.85)
            steps.append(sample(hwnd, f"c{cycle}-restored-api"))
            window.showNormal()
            time.sleep(0.35)
            steps.append(sample(hwnd, f"c{cycle}-restored-qt"))
            report["cycles"].append({"cycle": cycle, "steps": steps})

        path = os.path.join(OUT_DIR, "probe-minimize-cycle.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print("REPORT " + path)
        print(
            "SUMMARY "
            + json.dumps(
                {
                    "still_iconic_after_restore": [
                        item["cycle"]
                        for item in report["cycles"]
                        if item["cycle"] and item["steps"][-1]["iconic"]
                    ],
                    "title_band_means": [
                        [step["title_band_mean"] for step in item["steps"]]
                        for item in report["cycles"]
                    ],
                },
                ensure_ascii=False,
            )
        )
        app.quit()

    QTimer.singleShot(900, run)
    QTimer.singleShot(120_000, app.quit)
    app.exec()
    sandbox_env.cleanup(SANDBOX)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
