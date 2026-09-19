"""Save a screenshot of every page and dialog of the real Qt window.

The flash measurement says the window does not blank on restore; this says the
window still *looks* like the application.  Both are needed - a window that
paints nothing also never flickers.

Writes to ``out/tour-*.png``.  All persisted state is redirected, so this
cannot touch the user's real configuration.

    "C:/Program Files/Develop/Python/python.exe" prototypes/qt_visual_tour.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("qt-tour-")

from PIL import ImageGrab  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

import codex_config_qt as ui  # noqa: E402

OUT = HERE / "out"


def pump(app, seconds: float = 0.45) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def shoot(window, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # frameGeometry(), not x()/y() + width()/height(): for a window, Qt's
    # pos() already includes the frame while width()/height() are the client
    # size, so the naive box silently crops the bottom of the frame off.
    frame = window.frameGeometry()
    ImageGrab.grab(
        bbox=(frame.x(), frame.y(), frame.x() + frame.width(), frame.y() + frame.height())
    ).save(OUT / f"tour-{name}.png")
    print(f"  saved out/tour-{name}.png")


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
    window.raise_()
    window.activateWindow()
    pump(app, 1.0)

    print("pages:")
    for key in ("current", "profiles", "official", "guide", "recommended"):
        window.show_page(key)
        pump(app)
        shoot(window, key)

    print("dialogs:")
    dialogs = (
        ("about", lambda: ui.AboutDialog(window)),
        ("message-info", lambda: ui.MessageDialog(window, "已保存配置“demo”。", kind="info")),
        ("message-question", lambda: ui.MessageDialog(window, "应用配置需要正常退出并重新启动 Codex，是否继续？", kind="question")),
        ("profile-editor", lambda: ui.ProfileEditorDialog(window, None)),
        ("config-name", lambda: ui.ConfigNameDialog(window, CONFIG_DIR, "openai-配置", "新增配置：openai")),
        ("onboarding", lambda: ui.OnboardingDialog(window)),
        ("donation", lambda: ui.DonationDialog(window, window.donation_dialog_image)),
    )
    for name, factory in dialogs:
        dialog = factory()
        dialog.show()
        dialog.raise_()
        pump(app, 0.6)
        shoot(dialog, name)
        dialog.close()
        pump(app, 0.15)

    window.close()
    pump(app, 0.2)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
