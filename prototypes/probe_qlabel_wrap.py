"""Find the QLabel configuration that wraps like Tk's ``wraplength``.

``QLabel.setWordWrap(True)`` does not by itself make a vertical layout give the
label the extra height the wrapped text needs.  A label clamped to a narrower
width then *clips* its second line - which is worse than not wrapping at all,
because the text simply disappears mid-sentence.

This builds the same long string four ways inside a real QVBoxLayout and reports
the geometry each one ends up with.  Expected wrapped height is ~40px (two
lines at 9pt); a result of ~23px means the line is being clipped.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_qlabel_wrap.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("wrap-")

from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout  # noqa: E402

import codex_config_qt as ui  # noqa: E402

TEXT = "• 打开“新增配置”，填写配置名称、API Key、Provider 显示名称、Base URL 和启动默认模型。"
WRAP = 500


def variant_plain(label: QLabel) -> None:
    label.setWordWrap(True)


def variant_maxwidth(label: QLabel) -> None:
    label.setWordWrap(True)
    label.setMaximumWidth(WRAP)


def variant_fixedwidth(label: QLabel) -> None:
    label.setWordWrap(True)
    label.setFixedWidth(WRAP)


def variant_fixedwidth_policy(label: QLabel) -> None:
    label.setWordWrap(True)
    label.setFixedWidth(WRAP)
    policy = label.sizePolicy()
    policy.setHeightForWidth(True)
    label.setSizePolicy(policy)


def variant_minheight(label: QLabel) -> None:
    label.setWordWrap(True)
    label.setFixedWidth(WRAP)
    label.setMinimumHeight(label.heightForWidth(WRAP))


VARIANTS = (
    ("wordWrap only", variant_plain),
    ("+ maximumWidth", variant_maxwidth),
    ("+ fixedWidth", variant_fixedwidth),
    ("+ fixedWidth +policy", variant_fixedwidth_policy),
    ("+ fixedWidth +minHeight", variant_minheight),
)


def main() -> int:
    app = ui.create_application()
    window = QFrame()
    window.setObjectName("page")
    window.setStyleSheet(ui.APP_QSS)
    window.resize(620, 400)
    column = QVBoxLayout(window)
    column.setContentsMargins(20, 20, 20, 20)

    labels = []
    for name, apply in VARIANTS:
        holder = QLabel(f"[{name}]")
        holder.setObjectName("hint")
        column.addWidget(holder)
        label = QLabel(TEXT)
        label.setObjectName("bodyText")
        apply(label)
        column.addWidget(label)
        labels.append((name, label))

    window.show()
    deadline = time.time() + 1.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)

    print(f"{'variant':>24} {'width':>6} {'height':>7} {'hfw(500)':>9}  verdict")
    for name, label in labels:
        geo = label.geometry()
        hfw = label.heightForWidth(WRAP)
        verdict = "clipped" if geo.height() < 35 else "wrapped"
        print(f"{name:>24} {geo.width():>6} {geo.height():>7} {hfw:>9}  {verdict}")
    window.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
