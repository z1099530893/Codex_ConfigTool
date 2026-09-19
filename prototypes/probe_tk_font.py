"""Measure the *vertical* font metrics of both front ends, and derive the padding.

The horizontal side of this is settled (``probe_font_metrics.py``: the two
toolkits rasterise the same string at the same width).  The vertical side is
not, and it is the reason the port's pages sit a few pixels high:

    tk.Label   height = linespace * lines + 6
    QLabel     height = QFontMetrics.height() * lines + padding_top + padding_bottom

Tk's ``linespace`` measures exactly ``QFontMetrics.lineSpacing() + 2`` at every
size this app uses, while QLabel lays a line out at ``height()`` - which is
``lineSpacing() - leading``.  So the two disagree by ``leading + 2`` per line,
and every label role has to give that back as padding:

    required padding_v = (leading + 2) * lines + 6

For the 9pt/8pt regular roles ``leading`` is 0, so the answer is the 8px the
stylesheet already uses (``padding: 4px 0``) - which is why most labels match.
The bold roles have ``leading`` 1 and are 1px short; a *wrapped* label is 2px
short per extra line.

    "C:/Program Files/Develop/Python/python.exe" prototypes/probe_tk_font.py

Prints one row per (size, weight) the stylesheet uses, and a second table per
label role with the padding it should carry.

One trap, learned the hard way: do not try to recover the line count by dividing
``QLabel.heightForWidth(width)`` by the font height.  The stylesheet's
``padding: 4px 0`` is already inside ``heightForWidth``, so the division rounds a
two-line label up to three lines and the label is given 17px of phantom height.
``QFontMetrics.boundingRect(..., Qt.TextWordWrap, text)`` returns the wrapped
text box with no padding in it, which divides cleanly.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import sandbox_env  # noqa: E402

ROOT, CONFIG_DIR = sandbox_env.isolate("fonts-")

FAMILY = "Microsoft YaHei UI"
# Every (size, weight) the two stylesheets actually name, plus the 9pt default.
COMBOS = (
    (15, "bold"),
    (14, "bold"),
    (13, "bold"),
    (11, "bold"),
    (10, "bold"),
    (9, "bold"),
    (9, "normal"),
    (8, "normal"),
)
# A long CJK string and a short one, so "lines" can be 2 and 1 at wraplength 500.
LONG = "• 打开“新增配置”，填写配置名称、API Key、Provider 显示名称、Base URL 和启动默认模型。"
SHORT = "• 供应商是GPT或者OpenAI模型时，无需获取模型"
WRAP = 500


def tk_metrics() -> dict:
    import tkinter as tk
    import tkinter.font as tkfont

    root = tk.Tk()
    root.geometry("900x700")
    out = {}
    for size, weight in COMBOS:
        font = tkfont.Font(family=FAMILY, size=size, weight=weight)
        m = font.metrics()
        long_label = tk.Label(root, text=LONG, font=font, justify="left", anchor="w", wraplength=WRAP)
        long_label.pack(anchor="w")
        short_label = tk.Label(root, text=SHORT, font=font, justify="left", anchor="w", wraplength=WRAP)
        short_label.pack(anchor="w")
        root.update_idletasks()
        out[(size, weight)] = {
            "linespace": m["linespace"],
            "ascent": m["ascent"],
            "descent": m["descent"],
            "long_h": long_label.winfo_reqheight(),
            "short_h": short_label.winfo_reqheight(),
        }
    root.destroy()
    return out


def qt_metrics() -> dict:
    import codex_config_qt as ui  # noqa: F401  (installs the stylesheet)
    from PySide6.QtGui import QFont, QFontMetrics
    from PySide6.QtWidgets import QApplication, QLabel

    QApplication.instance() or ui.create_application()
    out = {}
    for size, weight in COMBOS:
        font = QFont(FAMILY)
        font.setPointSize(size)
        font.setWeight(QFont.Weight.Bold if weight == "bold" else QFont.Weight.Normal)
        fm = QFontMetrics(font)
        long_label = QLabel(LONG)
        long_label.setFont(font)
        long_label.setWordWrap(True)
        long_label.setFixedWidth(WRAP)
        long_label.ensurePolished()
        short_label = QLabel(SHORT)
        short_label.setFont(font)
        short_label.setWordWrap(True)
        short_label.setFixedWidth(WRAP)
        short_label.ensurePolished()
        out[(size, weight)] = {
            "height": fm.height(),
            "lineSpacing": fm.lineSpacing(),
            "leading": fm.leading(),
            "long_h": long_label.heightForWidth(WRAP),
            "short_h": short_label.heightForWidth(WRAP),
        }
    return out


def main() -> int:
    tk_rows = tk_metrics()
    qt_rows = qt_metrics()

    print("Tk's linespace vs Qt's line metrics (the glyph box, before any padding)")
    print(f"{'size/weight':>12} {'tk linespace':>12} {'qt height':>10} {'qt lineSpacing':>14} {'qt leading':>10} {'delta':>6}")
    for combo in COMBOS:
        tk_m = tk_rows[combo]
        qt_m = qt_rows[combo]
        print(
            f"{combo[0]:>4} {combo[1]:<6} {tk_m['linespace']:>12} {qt_m['height']:>10} "
            f"{qt_m['lineSpacing']:>14} {qt_m['leading']:>10} "
            f"{tk_m['linespace'] - qt_m['lineSpacing']:>6}"
        )

    print("\nLabel box: what each role has to pad by to reach Tk's height")
    print(
        f"{'size/weight':>12} {'lines':>6} {'tk long':>8} {'pad 1-line':>11} "
        f"{'pad n-line':>11} {'QSS has':>8}"
    )
    # What each role's rule currently carries in APP_QSS, as a total in px:
    # `padding: 4px 0` is 8, `3px 0` is 6, `5px 0 4px 0` is 9.  The point of the
    # column is that it should equal `pad 1-line` - if it does not, that role's
    # single-line labels are the wrong height.
    current = {
        (13, "bold"): 9,  # pageTitle
        (10, "bold"): 9,  # sectionTitle, channelTitle
        (11, "bold"): 6,  # bigStatus
        (9, "bold"): 8,  # panelHeading
        (9, "normal"): 8,  # bodyText, fieldLabel, channelUrl
        (8, "normal"): 8,  # hint, pageSubtitle
    }
    for combo in COMBOS:
        tk_m = tk_rows[combo]
        qt_m = qt_rows[combo]
        # Qt's content height for n lines is height() * n, so the padding is the
        # difference.  Derive the line count from Tk's own height rather than
        # assuming the long sample wraps to two lines - at 15pt it wraps to three.
        lines = max(1, round((tk_m["long_h"] - 6) / tk_m["linespace"]))
        pad1 = tk_m["short_h"] - qt_m["height"]
        padn = tk_m["long_h"] - qt_m["height"] * lines
        has = current.get(combo)
        mark = "" if has is None or has == pad1 else "  <-- mismatch"
        print(
            f"{combo[0]:>4} {combo[1]:<6} {lines:>6} {tk_m['long_h']:>8} "
            f"{pad1:>11} {padn:>11} {'' if has is None else has:>8}{mark}"
        )
    print(
        "\nA role needs `pad 1-line` for its single-line labels and `pad n-line` for a\n"
        "label that wraps to n lines - one padding value cannot do both, so a wrapped\n"
        "label has to have its height pinned in code.  The bold roles need 9 against the\n"
        "8 they carry, which is why they sit 1px high; an odd total cannot be written\n"
        "symmetrically, hence `padding: 5px 0 4px 0`."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        sandbox_env.cleanup(ROOT)
