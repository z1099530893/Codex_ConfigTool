"""Serve the *shipping* Qt window for the restore-flash harness.

``proto_restore_flash.py --framework qt-app`` launches this instead of the
prototype stand-in, so the measurement is taken on the window the app actually
ships - same construction flags, same widget tree, same style sheet.

Prints ``SERVE_HWND=<hex>`` on stdout, then runs the Qt event loop.

Everything that could touch the user's machine or perturb the measurement is
suppressed: all persisted state goes to a temp directory (see
``sandbox_env``) and the two startup timers - the onboarding dialog and the
update check - are disabled, because a modal dialog or a network call would
both perturb the timing and mutate state.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("qt-app-measure-")

import codex_config_qt as ui  # noqa: E402


def main() -> int:
    app = ui.create_application()

    ui.CodexConfigWindow._load_initial_path = lambda self: (
        self._set_path(CONFIG_DIR),
        self.load_path(CONFIG_DIR),
    )
    ui.CodexConfigWindow.show_onboarding_dialog = lambda self, force=False: None
    ui.CodexConfigWindow.check_for_updates_on_startup = lambda self: None

    window = ui.CodexConfigWindow()
    window.show()
    app.processEvents()

    print(f"SERVE_HWND={int(window.winId()):#x}", flush=True)
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
