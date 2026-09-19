"""Compare the button order of every dialog between the Tk and Qt front ends.

Why this exists: the 是/否 pair in the confirm dialog and the onboarding dialog
came out **mirrored** in the Qt port - 否 | 是 where Tk produces 是 | 否.  Nothing
caught it, and the reason is worth keeping: the Qt code added the buttons in the
same order Tk *creates* them, but Tk packs both with ``side="right"`` (so the
first one created ends up rightmost) while a ``QHBoxLayout`` lays widgets out in
the order they are added.  The two toolkits disagree about what "first" means, so
reading the two code paths side by side does not reveal it - the difference is in
the layout engine, not in the text or the call order.

So this measures instead of reading.  Each front end is driven in its own
subprocess (mixing a Tk root and a QApplication in one process invites event-loop
interference), and the two button orders are diffed.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_dialog_button_order.py

Needs an interpreter with BOTH tkinter and PySide6, so the system one.
Exit code 0 when every dialog matches, 1 when any differs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# HERE for ``sandbox_env``, ROOT for the application modules themselves.  Both are
# needed: the measurement subprocesses inherit neither from the parent's cwd.
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

QUESTION = "应用配置需要正常退出并重新启动 Codex，是否继续？"
VERBOSE = os.environ.get("BTNORDER_VERBOSE") == "1"


# --------------------------------------------------------------------------- #
# Tk
# --------------------------------------------------------------------------- #

def measure_tk() -> dict[str, list[str]]:
    """Open the real Tk dialogs and read where their buttons landed."""
    import tkinter as tk
    from tkinter import ttk

    import sandbox_env
    import codex_config_tool as core

    root, config_dir = sandbox_env.isolate("btnorder-")
    results: dict[str, list[str]] = {}

    def button_order(dialog) -> list[str]:
        found: list[tuple[int, str]] = []

        def walk(widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    text = child.cget("text")
                    if text:
                        found.append((child.winfo_rootx(), text))
                walk(child)

        walk(dialog)
        found.sort()
        if VERBOSE:
            print(f"    raw (rootx, text) = {found}", file=sys.stderr)
        # Refuse to return an order derived from equal sort keys: that is creation
        # order wearing the costume of a layout measurement.
        if len(found) > 1 and len({x for x, _ in found}) == 1:
            return ["<layout never resolved>"]
        return [text for _x, text in found]

    def pump(app, dialog=None) -> None:
        for _ in range(6):
            if dialog is not None and dialog.winfo_exists():
                dialog.update_idletasks()
                dialog.update()
            app.update_idletasks()
            app.update()

    def pump_until_mapped(app, dialog, timeout: float = 3.0) -> bool:
        """Drive the event loop until the dialog is really on screen.

        Not politeness - it is the difference between a measurement and a
        fabrication.  ``winfo_rootx()`` on a widget the geometry manager has not
        placed yet returns the **toplevel's** x, so every button comes back with
        the same value; sorting those equal keys silently degrades to creation
        order, which is a plausible-looking answer that happens to be wrong.  That
        is exactly how this probe first reported Tk's order backwards.
        """
        import time as _time

        deadline = _time.time() + timeout
        while _time.time() < deadline:
            pump(app, dialog)
            if dialog.winfo_exists() and dialog.winfo_ismapped():
                return True
        return False

    try:
        # Keep construction off the user's real state and away from the network.
        core.CodexConfigApp._load_initial_path = lambda self: (
            self.path_var.set(str(config_dir)),
            self.load_path(config_dir),
        )
        core.CodexConfigApp.check_for_updates_on_startup = lambda self: None
        real_onboarding = core.CodexConfigApp.show_onboarding_dialog
        core.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None

        app = core.CodexConfigApp()
        # Deliberately NOT withdrawn.  Every dialog here calls
        # ``dialog.transient(self)``, and a transient window whose master is
        # withdrawn is never mapped - so its children are never placed and
        # ``winfo_rootx()`` returns the toplevel's x for all of them.  Hiding the
        # main window to be tidy costs the measurement its validity.
        pump(app)

        # ``show_custom_dialog`` blocks in ``wait_window`` until the dialog is
        # destroyed, so measuring has to happen from inside that wait.
        def measuring_wait(dialog) -> None:
            mapped = pump_until_mapped(app, dialog)
            if VERBOSE:
                print(
                    f"    dialog mapped={mapped} geom={dialog.winfo_geometry()}",
                    file=sys.stderr,
                )
            results["show_custom_dialog(question)"] = button_order(dialog)
            dialog.destroy()

        app.wait_window = measuring_wait
        app.show_custom_dialog(QUESTION, kind="question")
        pump(app)

        def measure_modal_method(label: str, method_name: str) -> None:
            """Call a dialog method that returns while its dialog is still up."""
            before = {
                w for w in app.winfo_children() if isinstance(w, tk.Toplevel)
            }
            try:
                getattr(app, method_name)()
            except Exception as error:  # noqa: BLE001
                results[label] = [f"<could not open: {type(error).__name__}>"]
                return
            pump(app)
            fresh = [
                w
                for w in app.winfo_children()
                if isinstance(w, tk.Toplevel) and w.winfo_exists() and w not in before
            ]
            if not fresh:
                results[label] = ["<no dialog appeared>"]
                return
            dialog = fresh[-1]
            pump_until_mapped(app, dialog)
            results[label] = button_order(dialog)
            dialog.destroy()
            pump(app)

        # The onboarding dialog is patched out during construction, so restore it
        # before trying to open it.
        core.CodexConfigApp.show_onboarding_dialog = real_onboarding
        measure_modal_method("show_onboarding_dialog", "show_onboarding_dialog")
        measure_modal_method("show_donation_dialog", "show_donation_dialog")

        app.destroy()
    finally:
        sandbox_env.cleanup(root)
    return results


# --------------------------------------------------------------------------- #
# Qt
# --------------------------------------------------------------------------- #

def measure_qt() -> dict[str, list[str]]:
    """Build each Qt dialog and read where its layout put the buttons."""
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    from PySide6.QtWidgets import QApplication, QPushButton

    import codex_config_qt as qt

    app = QApplication.instance() or QApplication([])
    results: dict[str, list[str]] = {}

    def button_order(dialog) -> list[str]:
        found: list[tuple[int, str]] = []
        for button in dialog.findChildren(QPushButton):
            if not button.text():
                continue
            found.append((button.mapTo(dialog, button.rect().topLeft()).x(), button.text()))
        found.sort()
        if VERBOSE:
            print(f"    raw (x, text) = {found}", file=sys.stderr)
        # Same guard as the Tk side: equal sort keys would silently degrade to
        # child order, which looks like an answer and is not one.
        if len(found) > 1 and len({x for x, _ in found}) == 1:
            return ["<layout never resolved>"]
        return [text for _x, text in found]

    def record(label: str, factory) -> None:
        try:
            dialog = factory()
        except Exception as error:  # noqa: BLE001
            results[label] = [f"<could not build: {type(error).__name__}>"]
            return
        dialog.show()
        app.processEvents()
        results[label] = button_order(dialog)
        dialog.close()
        dialog.deleteLater()
        app.processEvents()

    record("show_custom_dialog(question)",
           lambda: qt.MessageDialog(None, QUESTION, kind="question"))
    record("show_onboarding_dialog", lambda: qt.OnboardingDialog(None))
    record("show_donation_dialog", lambda: qt.DonationDialog(None, None))
    return results


# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=["tk", "qt"], help="internal: measure one side")
    parser.add_argument("--json", action="store_true", help="internal: emit JSON only")
    args = parser.parse_args()

    if args.framework:
        data = measure_tk() if args.framework == "tk" else measure_qt()
        print(json.dumps(data, ensure_ascii=False))
        return 0

    orders: dict[str, dict[str, list[str]]] = {}
    for framework in ("tk", "qt"):
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--framework", framework, "--json"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        try:
            orders[framework] = json.loads(line)
        except json.JSONDecodeError:
            orders[framework] = {}
            print(f"  ({framework} measurement failed)")
            if proc.stderr.strip():
                print("   " + proc.stderr.strip().splitlines()[-1])

    keys = sorted(set(orders.get("tk", {})) | set(orders.get("qt", {})))
    width = max((len(k) for k in keys), default=10)
    print(f"{'dialog':<{width}}  {'Tk':<28} {'Qt':<28} verdict")
    print("-" * (width + 62))
    mismatched: list[str] = []
    compared = 0
    for key in keys:
        tk_order = orders.get("tk", {}).get(key, ["<missing>"])
        qt_order = orders.get("qt", {}).get(key, ["<missing>"])
        # An entry either side could not measure is *inconclusive*, not equal.
        # Comparing two "<could not build>" markers would report a confident OK
        # for a dialog that was never looked at - the same "green verdict on no
        # data" failure this script already guards against at the run level.
        # An empty list counts too: two dialogs with no detectable buttons are
        # not "in the same order", they are two dialogs with nothing to compare
        # (the donation dialog is exactly that - it has no buttons at all).
        inconclusive = (
            not tk_order
            or not qt_order
            or any(part.startswith("<") for part in tk_order + qt_order)
        )
        if inconclusive:
            verdict = "SKIP (not measured)"
        else:
            compared += 1
            ok = tk_order == qt_order
            if not ok:
                mismatched.append(key)
            verdict = "OK" if ok else "DIFFERS"
        print(
            f"{key:<{width}}  {' | '.join(tk_order):<28} {' | '.join(qt_order):<28} {verdict}"
        )

    print()
    # A run that measured nothing must not report success.  The first version of
    # this script printed "ALL DIALOGS MATCH" over an empty table because both
    # subprocesses had died on an ImportError - a green verdict on no data, which
    # is worse than a red one.  Require evidence before claiming agreement.
    empty = [name for name in ("tk", "qt") if not orders.get(name)]
    if empty:
        print(f"NO MEASUREMENTS from: {', '.join(empty)} - the run proved nothing")
        print("(both sides must report at least one dialog before agreement means anything)")
        return 1
    if compared == 0:
        print("NO DIALOG WAS CONCLUSIVELY COMPARED - the run proved nothing")
        return 1
    if mismatched:
        print(f"BUTTON ORDER DIFFERS: {', '.join(mismatched)}")
        print("Tk packs with side=\"right\" (first created ends up rightmost); a QHBoxLayout")
        print("lays widgets out in add order. Add Qt buttons in Tk's *visual* order.")
        return 1
    print(f"ALL COMPARED DIALOGS MATCH ({compared} of {len(keys)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
