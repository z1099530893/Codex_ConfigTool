"""Does a synthetic ``SC_MAXIMIZE`` resize the window?  Ask both front ends.

Requirement 3 is "minimise only, never maximise".  Both builds implement it the
same way: ``WS_MAXIMIZEBOX`` is never set, so the shell offers no maximise
button and no system-menu item.  But ``WS_MAXIMIZEBOX`` only governs the
*button* and the *menu entry* - ``DefWindowProc`` honours ``WM_SYSCOMMAND`` /
``SC_MAXIMIZE`` regardless of it.  So a synthetic ``SC_MAXIMIZE`` (which is what
Win+Up sends) tests something the style bits do not cover.

This probe exists to answer one question with evidence rather than inference:
does the Tk build resist it, or does it have the same hole?  If both behave
identically then the Qt port has not regressed anything, and the finding belongs
to the project rather than to the port.

Both windows are built in-process and pointed at a throwaway directory, so
nothing the user owns is touched.

Usage:
    python probe_sc_maximize.py            # both, one after the other
    python probe_sc_maximize.py --only qt
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import sandbox_env  # noqa: E402

SANDBOX, CONFIG_DIR = sandbox_env.isolate("codex-sc-maximize-")

import winapi as W  # noqa: E402

import codex_config_tool as core  # noqa: E402

OUT_DIR = os.path.join(HERE, "out")


def seed() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    core.write_text(
        CONFIG_DIR / "config.toml",
        core.build_fresh_config_toml("sk-probe", core.DEFAULT_PROVIDER, core.DEFAULT_BASE_URL),
    )
    core.update_auth_json(CONFIG_DIR / "auth.json", "sk-probe")


def measure(hwnd: int) -> dict:
    return {
        "window_rect": list(W.window_rect(hwnd)),
        "client": list(W.client_rect(hwnd)),
        "style": hex(W.get_style(hwnd)),
        "maximize_box": bool(W.get_style(hwnd) & W.WS_MAXIMIZEBOX),
        "maximize_menu_item": (W.system_menu_report(hwnd).get("items") or {}).get("maximize"),
    }


def report(tag: str, hwnd: int, before: dict, after_sc: dict, after_show: dict) -> dict:
    """Both paths, because they are stopped by different mechanisms.

    ``SC_MAXIMIZE`` is a *command*: it can be dropped before ``DefWindowProc``
    sees it.  ``ShowWindow(SW_SHOWMAXIMIZED)`` sets ``WS_MAXIMIZE`` directly, so
    nothing can intercept it - only noticing the resulting resize and undoing it
    works.
    """
    resized_sc = after_sc["client"] != before["client"]
    resized_show = after_show["client"] != before["client"]
    print(
        f"[{tag}] client {before['client']}"
        f" -> SC_MAXIMIZE {after_sc['client']}"
        f" -> SW_SHOWMAXIMIZED {after_show['client']}  "
        f"maximize_box={before['maximize_box']} menu={before['maximize_menu_item']!r}  "
        f"resized_sc={resized_sc} resized_show={resized_show}"
    )
    return {
        "framework": tag,
        "before": before,
        "after_sc_maximize": after_sc,
        "after_show_maximized": after_show,
        "resized_by_sc_maximize": resized_sc,
        "resized_by_show_maximized": resized_show,
    }


def probe_tk() -> dict:
    import tkinter  # noqa: F401  (import for its side effect of being present)

    import codex_config_tool as module

    module.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    module.CodexConfigApp.check_for_updates_on_startup = lambda self: None
    module.CodexConfigApp._load_initial_path = lambda self: None

    app = module.CodexConfigApp()
    result: dict = {}

    def run() -> None:
        hwnd = app._window_handle()
        before = measure(hwnd)
        ctypes.windll.user32.SendMessageW(hwnd, W.WM_SYSCOMMAND, W.SC_MAXIMIZE, 0)
        app.update()
        time.sleep(0.6)
        app.update()
        after_sc = measure(hwnd)
        W.restore_window(hwnd)
        app.update()
        time.sleep(0.5)
        ctypes.windll.user32.ShowWindow(hwnd, W.SW_SHOWMAXIMIZED)
        app.update()
        time.sleep(0.6)
        app.update()
        after_show = measure(hwnd)
        result.update(report("tk", hwnd, before, after_sc, after_show))
        app.quit()
        app.destroy()

    app.after(800, run)
    app.after(20_000, lambda: (app.quit(), app.destroy()))
    try:
        app.mainloop()
    except Exception:  # noqa: BLE001
        pass
    return result


def probe_qt() -> dict:
    from PySide6.QtCore import QTimer

    import codex_config_qt as view

    view.CodexConfigWindow.show_onboarding_dialog = lambda self, force=False: None
    view.CodexConfigWindow.check_for_updates_on_startup = lambda self: None
    view.CodexConfigWindow._load_initial_path = lambda self: None

    app = view.create_application()
    window = view.CodexConfigWindow()
    window.show()
    result: dict = {}

    def run() -> None:
        hwnd = int(window.winId())
        before = measure(hwnd)
        ctypes.windll.user32.SendMessageW(hwnd, W.WM_SYSCOMMAND, W.SC_MAXIMIZE, 0)
        app.processEvents()
        time.sleep(0.6)
        app.processEvents()
        after_sc = measure(hwnd)
        W.restore_window(hwnd)
        window.showNormal()
        app.processEvents()
        time.sleep(0.5)
        ctypes.windll.user32.ShowWindow(hwnd, W.SW_SHOWMAXIMIZED)
        app.processEvents()
        time.sleep(0.6)
        app.processEvents()
        time.sleep(0.3)
        app.processEvents()
        after_show = measure(hwnd)
        result.update(report("qt", hwnd, before, after_sc, after_show))
        app.quit()

    QTimer.singleShot(900, run)
    QTimer.singleShot(20_000, app.quit)
    app.exec()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=("tk", "qt"), default=None)
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    seed()

    results = []
    if args.only in (None, "tk"):
        results.append(probe_tk())
    if args.only in (None, "qt"):
        results.append(probe_qt())

    path = os.path.join(OUT_DIR, "probe-sc-maximize.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
    print("REPORT " + path)
    print(
        "SUMMARY "
        + json.dumps(
            {
                "resized_by_sc_maximize": {
                    item["framework"]: item["resized_by_sc_maximize"] for item in results
                },
                "resized_by_show_maximized": {
                    item["framework"]: item["resized_by_show_maximized"] for item in results
                },
                "both_behave_the_same": len(
                    {
                        (item["resized_by_sc_maximize"], item["resized_by_show_maximized"])
                        for item in results
                    }
                )
                <= 1,
            },
            ensure_ascii=False,
        )
    )
    sandbox_env.cleanup(SANDBOX)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
