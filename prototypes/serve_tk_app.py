"""Serve the *shipping* Tk window for the restore-flash harness.

``proto_restore_flash.py --framework tk-app`` launches this, so the "before"
side of the comparison is the real ``codex_config_tool.CodexConfigApp`` rather
than the prototype stand-in.

That matters, because the Qt build reuses the Tk palette and the same geometry
(142px sidebar, 38px title bar, five 42px nav rows), so a single ``--strip-top``
is valid for both and the two sets of numbers are directly comparable - a true
before/after on the same program rather than on two stand-ins.

All persisted state is redirected (see ``sandbox_env``) and the startup timers
are disabled, exactly as in ``serve_qt_app.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("tk-app-measure-")

import codex_config_tool as core  # noqa: E402


def main() -> int:
    core.CodexConfigApp._load_initial_path = lambda self: (
        self.path_var.set(str(CONFIG_DIR)),
        self.load_path(CONFIG_DIR),
    )
    core.CodexConfigApp.show_onboarding_dialog = lambda self, force=False: None
    core.CodexConfigApp.check_for_updates_on_startup = lambda self: None

    app = core.CodexConfigApp()
    for _ in range(3):
        app.update_idletasks()
        app.update()

    hwnd = app._window_handle()
    print(f"SERVE_HWND={hwnd:#x}", flush=True)
    app.mainloop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
