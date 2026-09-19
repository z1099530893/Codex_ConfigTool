"""Print the rendered width of the same string under both front ends' fonts.

The Qt port's text was coming out narrower than Tk's for the same nominal point
size, which changes where lines wrap and therefore how tall the panels are.  A
label height cannot settle this - Tk's tk.Label and Qt's QLabel add different
padding - so measure the *glyphs*.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_font_metrics.py

Both sides are asked for the natural (size-hint) width of identical strings.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("fonts-")

# The strings whose wrapping differs, plus a plain-width control.
SAMPLES = (
    ("welcome-8pt", 8, "欢迎使用Codex配置助手，如果觉得软件好用，请点击左侧二维码并扫描，支持作者。"),
    ("bullet1-9pt", 9, "• 打开“新增配置”，填写配置名称、API Key、Provider 显示名称、Base URL 和启动默认模型。"),
    ("bullet2-9pt", 9, "• 供应商是GPT或者OpenAI模型时，无需获取模型"),
    ("latin-9pt", 9, "Provider 显示名称"),
    ("ascii-9pt", 9, "https://api.openai.com/v1"),
)


def tk_widths() -> dict:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    out = {}
    for name, size, text in SAMPLES:
        label = tk.Label(root, text=text, font=("Microsoft YaHei UI", size))
        out[name] = (label.winfo_reqwidth(), label.winfo_reqheight())
    root.destroy()
    return out


def qt_widths() -> dict:
    import codex_config_qt as ui
    from PySide6.QtWidgets import QLabel

    app = ui.create_application()
    out = {}
    for name, size, text in SAMPLES:
        label = QLabel(text)
        label.setObjectName("bodyText" if size == 9 else "pageSubtitle")
        label.setWordWrap(False)
        label.ensurePolished()
        hint = label.sizeHint()
        out[name] = (hint.width(), hint.height())
    return out


def main() -> int:
    tk_rows = tk_widths()
    qt_rows = qt_widths()

    print(f"{'sample':>14} {'tk w':>6} {'qt w':>6} {'ratio':>7}   {'tk h':>5} {'qt h':>5}")
    for name, _size, _text in SAMPLES:
        tw, th = tk_rows[name]
        qw, qh = qt_rows[name]
        ratio = qw / tw if tw else 0
        print(f"{name:>14} {tw:>6} {qw:>6} {ratio:>7.3f}   {th:>5} {qh:>5}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
