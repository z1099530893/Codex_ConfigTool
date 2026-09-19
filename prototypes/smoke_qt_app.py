"""Structural smoke test for :class:`codex_config_qt.CodexConfigWindow`.

Builds the real Qt window against a throwaway config directory, then checks the
things that must hold for the flicker fix to be real:

* the window is 820x500 and frameless;
* every page and nav item exists and page switching works;
* **the toplevel owns no native child windows** - that is the property that
  makes one surface plus a backing store possible, and therefore the property
  that removes the restore flash;
* every dialog can be constructed without raising.

The real settings file is snapshotted and restored, and the real ``~/.codex``
is never touched: ``_load_initial_path`` is redirected to a temp directory.

Run with the system Python (it has both tkinter, which ``codex_config_tool``
imports, and PySide6)::

    "C:/Program Files/Develop/Python/python.exe" prototypes/smoke_qt_app.py
"""

from __future__ import annotations

import ctypes
import shutil
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import codex_config_tool as core  # noqa: E402

_SETTINGS_FILE = core.SETTINGS_FILE
_SETTINGS_BACKUP = _SETTINGS_FILE.read_bytes() if _SETTINGS_FILE.exists() else None

from PySide6.QtCore import Qt  # noqa: E402

import codex_config_qt as ui  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    if not condition:
        FAILURES.append(label)


# -- Win32 child enumeration ------------------------------------------------

user32 = ctypes.windll.user32
user32.EnumChildWindows.argtypes = (
    wintypes.HWND,
    ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
)
user32.EnumChildWindows.restype = ctypes.c_bool
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = wintypes.LONG
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL

GWL_EXSTYLE = -20
GWL_STYLE = -16


def native_children(hwnd: int) -> list[int]:
    found: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def collect(child, _param):
        found.append(int(child))
        return True

    user32.EnumChildWindows(hwnd, callback_type(collect), 0)
    return found


def class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


# -- the test ---------------------------------------------------------------

def main() -> int:
    app = ui.create_application()

    workdir = Path(tempfile.mkdtemp(prefix="qt-smoke-"))
    config_dir = workdir / ".codex"

    # Never touch the real ~/.codex, and never let the startup timers fire.
    ui.CodexConfigWindow._load_initial_path = lambda self: (
        self._set_path(config_dir),
        self.load_path(config_dir),
    )
    ui.CodexConfigWindow.show_onboarding_dialog = lambda self, force=False: None
    ui.CodexConfigWindow.check_for_updates_on_startup = lambda self: None

    print("building window")
    window = ui.CodexConfigWindow()
    window.show()
    app.processEvents()

    def census(label: str) -> int:
        hwnd_now = int(window.winId())
        kids = native_children(hwnd_now)
        kinds: dict[str, int] = {}
        for child in kids:
            name = class_name(child)
            kinds[name] = kinds.get(name, 0) + 1
        print(f"  {label}: native children = {len(kids)}")
        for name, count in sorted(kinds.items()):
            print(f"      {name}: {count}")
        return len(kids)

    print("\n-- native window census (the flicker property) --")
    print(
        "  measured before any dialog has ever been constructed: a QDialog given a\n"
        "  parent is still a top-level window and registers its own hidden icon\n"
        "  helper, which would otherwise show up here and say nothing about the\n"
        "  window the restore flash is actually measured in."
    )
    check(census("shipping state") == 0, "toplevel owns no native child windows")

    print("\n-- window --")
    check(window.width() == core.WINDOW_WIDTH and window.height() == core.WINDOW_HEIGHT,
          "size is 820x500", f"{window.width()}x{window.height()}")
    flags = window.windowFlags()
    check(bool(flags & Qt.WindowType.FramelessWindowHint), "FramelessWindowHint is set")
    check(window.windowTitle() == core.APP_NAME, "title matches APP_NAME")

    print("\n-- pages and navigation --")
    expected_pages = {"current", "profiles", "official", "guide", "recommended"}
    check(set(window.pages) == expected_pages, "all five pages exist", str(sorted(window.pages)))
    check(set(window.nav_items) == expected_pages, "all five nav items exist")
    for key in ("profiles", "official", "guide", "recommended", "current"):
        window.show_page(key)
        app.processEvents()
        ok = window.active_page == key and window.page_host.currentWidget() is window.pages[key]
        check(ok, f"show_page({key!r}) switches the stack")
    for key in expected_pages:
        selected = window.nav_items[key].isChecked()
        check(selected == (key == "current"), f"nav highlight for {key!r}", str(selected))

    print("\n-- config directory --")
    check(window.current_path() == core.canonical_config_path(config_dir),
          "current_path() tracks the loaded directory", str(window.current_path()))
    check(window.path_edit.text() == str(core.canonical_config_path(config_dir)),
          "path field shows the directory")

    print("\n-- profile table --")
    window.show_page("profiles")
    app.processEvents()
    check(hasattr(window, "profile_table"), "profile table exists")
    check(window.profile_table.columnCount() == 2, "two columns")
    check(window.profile_empty_label.text() != "", "empty-state label is populated",
          window.profile_empty_label.text())
    check(not window.profile_switch_button.isEnabled(), "switch button disabled with no selection")

    print("\n-- key visibility toggle --")
    before = window.key_entry.echoMode()
    window.toggle_key_visibility()
    app.processEvents()
    check(window.key_entry.echoMode() != before, "echo mode flips",
          f"{before} -> {window.key_entry.echoMode()}")
    window.toggle_key_visibility()
    app.processEvents()
    check(window.key_entry.echoMode() == before, "echo mode flips back")

    print("\n-- toast --")
    window.notify("smoke test toast")
    app.processEvents()
    check(window._toast is not None and window._toast.isVisible(), "toast is shown")
    window._toast.close()
    app.processEvents()

    print("\n-- dialogs construct --")
    dialogs = [
        ("MessageDialog(info)", lambda: ui.MessageDialog(window, "hello", kind="info")),
        ("MessageDialog(error)", lambda: ui.MessageDialog(window, "boom", kind="error")),
        ("MessageDialog(question)", lambda: ui.MessageDialog(window, "sure?", kind="question")),
        ("ConfigNameDialog", lambda: ui.ConfigNameDialog(
            window, config_dir, "demo-profile", "新增配置：openai")),
        ("ScanPickerDialog", lambda: ui.ScanPickerDialog(window, [config_dir, workdir])),
        ("OnboardingDialog", lambda: ui.OnboardingDialog(window)),
        ("DonationDialog", lambda: ui.DonationDialog(window, window.donation_dialog_image)),
        ("AboutDialog", lambda: ui.AboutDialog(window)),
        ("ProfileEditorDialog(new)", lambda: ui.ProfileEditorDialog(window, None)),
    ]
    for label, factory in dialogs:
        try:
            dialog = factory()
            dialog.show()
            app.processEvents()
            dialog.close()
            app.processEvents()
            check(True, label)
        except Exception as exc:  # noqa: BLE001 - the point is to surface anything
            check(False, label, f"{exc.__class__.__name__}: {exc}")

    print("\n-- taskbar minimise / restore (the app's own button) --")
    window._set_appwindow_style(attempt=5)
    app.processEvents()
    check(window._taskbar_button_ready, "taskbar button registered with the shell")
    hwnd = int(window.winId())
    print(f"  toplevel hwnd = 0x{hwnd:08x}")
    print(
        f"  style   = 0x{user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF:08x}"
        "   (want WS_SYSMENU|WS_MINIMIZEBOX, and no WS_CAPTION / WS_THICKFRAME)"
    )
    print(
        f"  exstyle = 0x{user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF:08x}"
        "   (want WS_EX_APPWINDOW, and no WS_EX_LAYERED)"
    )
    check(not user32.IsIconic(hwnd), "window starts restored")
    window._minimize_window()
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)
    check(bool(user32.IsIconic(hwnd)), "the app's own minimise button iconifies the window")
    window.showNormal()
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)
    check(not user32.IsIconic(hwnd), "showNormal brings it back")

    print("\n-- native window census after the dialogs --")
    after = census("after dialogs")
    if after:
        print(
            "  note: these are Qt's per-top-level icon helpers.  A QDialog given a\n"
            "        parent is still a top-level window, and each one Qt creates\n"
            "        registers a hidden helper; they are not part of the main\n"
            "        window's surface and vanish with the dialog.  The shipping\n"
            "        state above - which is what the restore flash is measured in -\n"
            "        is the number that matters."
        )

    print("\n-- widget inventory --")
    widgets = window.findChildren(ui.QWidget)
    kinds: dict[str, int] = {}
    for widget in widgets:
        name = type(widget).__name__
        kinds[name] = kinds.get(name, 0) + 1
    print(f"  Qt widgets in the tree: {len(widgets)}")
    for name, count in sorted(kinds.items(), key=lambda item: -item[1]):
        print(f"      {name}: {count}")

    window.close()
    app.processEvents()
    shutil.rmtree(workdir, ignore_errors=True)

    print("\n" + "=" * 62)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for item in FAILURES:
            print(f"  - {item}")
    else:
        print("ALL CHECKS PASSED")
    print("=" * 62)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        if _SETTINGS_BACKUP is None:
            _SETTINGS_FILE.unlink(missing_ok=True)
        else:
            _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SETTINGS_FILE.write_bytes(_SETTINGS_BACKUP)
    sys.exit(code)
