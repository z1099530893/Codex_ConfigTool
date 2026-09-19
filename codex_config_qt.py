"""Qt front end for Codex 配置助手.

Why this file exists
--------------------
The Tk build flashes the whole main window when it is restored from the
taskbar.  Over nine measurement rounds (see ``AGENT_HANDOFF_WINDOW_BUGS.md``)
the mechanism turned out to be structural rather than a bug in this app:

* A Tk top level owns **no backing store**.  On restore the window's surface is
  presented before any of its content has been repainted, so the compositor
  shows the toplevel's own background for one to three frames.  Collapsing the
  Tk view layer onto a single ``Canvas`` cuts that roughly in half (17/241 ->
  8/240 blank frames) but cannot remove it; layering does not change it at all.
* A Qt top level owns **both** halves of what is missing - one surface, and a
  backing store it blits on demand - so a restore presents the last complete
  frame with no blank interval.  Measured with the same probe on the same UI:
  **0 blank frames out of 240**, against 8/240 for the best Tk variant.

So this module rebuilds the *view* in Qt while importing every piece of
non-visual behaviour from :mod:`codex_config_tool` unchanged.  That module is
deliberately left byte-identical so it stays the rollback.

What is reused verbatim from ``codex_config_tool``
--------------------------------------------------
Everything below ``CodexConfigApp`` - config parsing and writing, backup and
profile management, process handling, the update check, the Win32 window
helpers, settings, resources.  This file contains no new business logic; it is
a view layer plus the small amount of glue needed to drive it.

Deliberate simplifications, each a replacement rather than a removal
-------------------------------------------------------------------
* The custom smooth horizontal scrolling inside long API Key fields is gone.
  ``QLineEdit`` already keeps the cursor visible and auto-scrolls during a
  drag-select; the Tk version had to implement that by hand.
* The hand-drawn combobox drop-down arrow is gone; ``QComboBox`` draws its own.
* The hand-rolled multi-select drag in the profile list is gone;
  ``QTableWidget``'s ``ExtendedSelection`` gives the same click/shift/ctrl
  behaviour natively.
* ``ttk`` stylesheets become one Qt style sheet; no behaviour depends on them.

Deliberate strictness
---------------------
One requirement is implemented more strictly here than in the build this
replaces: "minimise only, never maximise".  Both builds leave
``WS_MAXIMIZEBOX`` unset, which removes the maximise button and the system-menu
entry - but it does not stop the *command*.  ``DefWindowProc`` honours
``WM_SYSCOMMAND``/``SC_MAXIMIZE`` regardless of the style, and
``prototypes/probe_sc_maximize.py`` measures a synthetic ``SC_MAXIMIZE``
resizing the Tk build to 1920x1080.  This build refuses it in
:meth:`CodexConfigWindow.nativeEvent` and reverts an externally-set maximised
state in :meth:`CodexConfigWindow.resizeEvent`, so Win+Up and even a direct
``ShowWindow(SW_SHOWMAXIMIZED)`` leave the window at 820x500.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import codex_config_tool as core


# --------------------------------------------------------------------------
# Palette and metrics - lifted from CodexConfigApp._build_style so the Qt build
# is visually the same application.
# --------------------------------------------------------------------------

FONT_FAMILY = "Microsoft YaHei UI"

BG = "#f3f4f7"
PANEL = "#ffffff"
PANEL_BORDER = "#eceef1"
TEXT = "#20242b"
TEXT_STRONG = "#171a20"
TEXT_LABEL = "#303640"
TEXT_MUTED = "#69707d"
BORDER = "#d8dde3"
FIELD_BG = "#f7f8f9"
FIELD_TEXT = "#343a43"

SIDEBAR = "#5b5b5b"
SIDEBAR_HOVER = "#666666"
SIDEBAR_SELECTED = "#eceeef"
ACCENT = "#2f6f5e"
ACCENT_HOVER = "#285f51"
BRAND_GREEN = "#2e9b63"
DANGER_TEXT = "#a33a32"

TITLEBAR = "#000000"
TITLEBAR_HOVER = "#292929"
CLOSE_HOVER = "#c42b1c"

TITLE_HEIGHT = 38
SIDEBAR_WIDTH = 142
NAV_ROW_HEIGHT = 42
# ``CodexConfigApp._create_nav_item`` puts a ``tk.Label(width=1)`` indicator at
# the left of every row and gives the button ``padx=24``; the indicator measures
# 13px and the caption therefore starts at 13 + 24 = 37.  Drawing the indicator
# 1px wide and starting the text at 25 loses the block *and* shifts every
# caption 12px left.
NAV_INDICATOR_WIDTH = 13
NAV_TEXT_LEFT = 37

APP_QSS = f"""
QWidget {{
    font-family: "{FONT_FAMILY}";
    font-size: 9pt;
    color: {TEXT};
}}
QWidget#shell, QWidget#pageHost, QWidget#page {{ background: {BG}; }}
QFrame#titleBar {{ background: {TITLEBAR}; }}
QFrame#sidebar {{ background: {SIDEBAR}; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {PANEL_BORDER}; }}
QFrame#channelCard {{ background: {PANEL}; border: 1px solid #e2e5e8; }}
QFrame#channelCard:hover {{ border: 1px solid #cfd5da; }}
/* Tk uses two panel borders, not one: ``#eceef1`` for the generic page panels
   (``tk.Frame(highlightbackground="#eceef1")``) and ``#e2e5e8`` for the profile
   tree panel and the channel rows.  ``#panel`` is the generic one, so the tree
   panel needs its own role rather than borrowing it. */
QFrame#treePanel {{ background: {PANEL}; border: 1px solid #e2e5e8; }}
QFrame#separator {{ background: #eef0f2; border: none; }}

/* Every label role below carries the padding that makes its box the same
   height as the ``tk.Label`` it replaces.  Tk's box is
   ``linespace * lines + 6``; QLabel's is ``QFontMetrics.height() * lines``
   plus the stylesheet padding.  Tk's linespace measures exactly
   ``QFontMetrics.lineSpacing() + 2`` at every size this app uses, and QLabel
   lays a line out at ``height()`` rather than ``lineSpacing()`` - so a role
   is short by ``leading + 2`` per line:

       required padding = (leading + 2) * lines + 6

   The regular 9pt and 8pt roles have ``leading`` 0, so 8px - the ``4px 0``
   they already carry - is exactly right.  The bold roles have ``leading`` 1
   and need 9px, which is why they were the ones sitting 1px high.  Odd totals
   cannot be written symmetrically, hence the 5/4 splits.
   prototypes/probe_tk_font.py prints both front ends' metrics for every size.
   11pt bold is the one size where Tk's linespace equals Qt's, so ``bigStatus``
   needs 6px rather than 8 - it is correct as it stands. */
QLabel#titleText {{ color: #f4f4f4; }}
QLabel#pageTitle {{ font-size: 13pt; font-weight: bold; color: {TEXT_STRONG}; padding: 5px 0 4px 0; }}
QLabel#pageSubtitle {{ font-size: 8pt; color: {TEXT_MUTED}; padding: 4px 0; }}
QLabel#fieldLabel {{ color: {TEXT_LABEL}; padding: 4px 0; }}
/* Tk draws this one at 8pt bold (``font=("Microsoft YaHei UI", 8, "bold")``);
   without the size it inherited the 9pt default and came out a point large. */
QLabel#panelHeading {{ color: #2a3038; font-size: 8pt; font-weight: bold; padding: 4px 0; }}
QLabel#hint {{ color: {TEXT_MUTED}; font-size: 8pt; padding: 4px 0; }}
QLabel#bodyText {{ color: #4f5865; padding: 4px 0; }}
QLabel#bodyTextWarn {{ color: #8b2f2a; padding: 4px 0; }}
QLabel#sectionTitle {{ color: {TEXT}; font-size: 10pt; font-weight: bold; padding: 5px 0 4px 0; }}
QLabel#bigStatus {{ color: {TEXT}; font-size: 11pt; font-weight: bold; padding: 3px 0; }}
QLabel#channelTitle {{ color: {TEXT}; font-size: 10pt; font-weight: bold; padding: 5px 0 4px 0; }}
QLabel#channelUrl {{ color: {ACCENT}; padding: 4px 0; }}
/* Tk gives the icon a 36x36 image plus a 2px label border on each side. */
QLabel#channelIcon {{ background: #eef5f2; color: #355d52; font-weight: bold; padding: 2px; }}
QLabel#errorText {{ color: {DANGER_TEXT}; font-size: 8pt; }}
QLabel#aboutLink {{ color: {ACCENT}; }}
/* The current-config heading is drawn with ``borderwidth=0`` in Tk, so its box
   is ``linespace + 2`` rather than ``linespace + 6``: 26px, not 30px. */
QLabel#currentName {{ color: {TEXT}; font-size: 13pt; font-weight: bold; padding: 3px 0 2px 0; }}

QPushButton#outline {{
    background: {PANEL}; border: 1px solid {BORDER};
    padding: 10px 12px; color: {TEXT_LABEL};
}}
QPushButton#outline:hover {{ background: #f4f6f7; }}
QPushButton#outline:pressed {{ background: #eceff1; }}
QPushButton#outline:disabled {{ background: #eceff1; color: #a0a6ad; }}
QPushButton#secondary {{
    background: #e8ecef; border: none; padding: 10px 12px; color: {TEXT_LABEL};
}}
QPushButton#secondary:hover {{ background: #dfe4e7; }}
QPushButton#secondary:pressed {{ background: #d7dde1; }}
QPushButton#secondary:disabled {{ background: #eceff1; color: #a0a6ad; }}
QPushButton#primary {{
    background: {ACCENT}; color: #ffffff; border: none;
    padding: 8px 14px; font-weight: bold;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #aeb8b4; }}
QPushButton#danger {{
    background: {PANEL}; border: 1px solid {BORDER};
    padding: 10px 12px; color: {DANGER_TEXT};
}}
QPushButton#danger:hover {{ background: #faf1f0; }}
QPushButton#danger:disabled {{ background: #eceff1; color: #a0a6ad; border: 1px solid #e4e8ea; }}

QLineEdit {{
    background: {FIELD_BG}; border: 1px solid {BORDER};
    padding: 8px 6px; color: {FIELD_TEXT};
    selection-background-color: {ACCENT}; selection-color: #ffffff;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit[readOnly="true"] {{ background: {FIELD_BG}; color: {FIELD_TEXT}; }}
QLineEdit#searchField {{ background: #ffffff; }}

QComboBox {{
    background: {FIELD_BG}; border: 1px solid #a8adb2;
    padding: 8px 34px 8px 6px; color: {FIELD_TEXT};
}}
QComboBox:focus {{ border: 1px solid {ACCENT}; }}
/* ``ModelComboBox`` paints the arrow itself (see ``ComboArrowButton``), so the
   sub-control is kept only to reserve Tk's 34px text inset - width 0 would let
   long model names slide underneath the arrow - and is drawn as nothing at all.
   ``image: none`` plus a zero-sized arrow is what removes the native bevel. */
QComboBox::drop-down {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 34px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; border: none; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT}; selection-color: #ffffff;
    outline: none;
}}

QTableWidget {{
    background: {PANEL}; border: none; gridline-color: transparent;
    selection-background-color: #dce9e4; selection-color: #1d332c;
    outline: none;
}}
QTableWidget::item {{ padding-left: 6px; }}
QHeaderView::section {{
    /* Sampled down a column, Tk's heading band is 35px: 1px ``#9e9a91`` border,
       1px ``#eeebe7`` highlight, 31px ``#eef0f2``, 1px ``#cfcdc8`` shadow,
       1px ``#9e9a91`` border.  Only the flat fill is reproducible here - a QSS
       gradient cannot draw a 1px band inside a 33px box, because
       ``qlineargradient``'s stop positions are parsed as 0 or 1 and a fractional
       or percentage stop collapses the whole value to a flat colour (measured
       in ``probe_header_gradient.py``, which also shows the declaration being
       dropped silently rather than reported).  The two inner lines are 1px of
       near-white highlight and 1px of shadow, so what is left - the two borders,
       the column divider and the text - is what carries the header's weight. */
    background: #eef0f2; color: #343a43; font-weight: bold;
    /* Tk's ``Treeview.Heading`` is ``padding=(8, 7)`` with no border and comes
       out 35px tall.  A QSS border is added *outside* the padding, so matching
       Tk's border costs 2px of the padding - 7px would make the header 37px and
       push the whole table body down with it. */
    padding: 5px 8px;
    border: none;
    border-top: 1px solid #9e9a91;
    border-bottom: 1px solid #9e9a91;
    /* Tk's column separator measures three pixels - ``cfcdc8`` then
       ``9e9a91`` twice.  QSS can only draw one colour per border, so this is
       the dark two of the three; the leading light pixel is the part that has
       to go, and losing it costs less than drawing the whole divider in the
       light colour (which is what 1px ``cfcdc8`` did, and read as no divider
       at all). */
    border-right: 3px solid #9e9a91;
}}
QScrollBar:vertical {{ background: {PANEL}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #c9ced3; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #b3b9bf; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; }}
QMenu::item:selected {{ background: #eef2f1; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: #e6e9eb; margin: 4px 6px; }}
"""

DIALOG_QSS = f"""
QDialog {{ background: {BG}; }}
QLabel {{ color: {TEXT_LABEL}; }}
QLabel#dialogTitle {{ color: {TEXT_STRONG}; font-size: 14pt; font-weight: bold; }}
QLabel#dialogSubtitle {{ color: {TEXT_MUTED}; font-size: 8pt; }}
QLabel#hint {{ color: {TEXT_MUTED}; font-size: 8pt; }}
QLabel#errorText {{ color: {DANGER_TEXT}; font-size: 8pt; }}
QLabel#aboutLink {{ color: {ACCENT}; }}
QLabel#aboutTitle {{ color: {TEXT_STRONG}; font-size: 15pt; font-weight: bold; }}
QLabel#bigStatus {{ color: {TEXT}; font-size: 11pt; font-weight: bold; }}
QLabel#sectionTitle {{ color: {TEXT}; font-size: 10pt; font-weight: bold; }}
QPushButton#outline {{
    background: {PANEL}; border: 1px solid {BORDER};
    padding: 8px 12px; color: {TEXT_LABEL};
}}
QPushButton#outline:hover {{ background: #f4f6f7; }}
QPushButton#outline:pressed {{ background: #eceff1; }}
QPushButton#outline:disabled {{ background: #eceff1; color: #a0a6ad; }}
QPushButton#secondary {{
    background: #e8ecef; border: none; padding: 8px 12px; color: {TEXT_LABEL};
}}
QPushButton#secondary:hover {{ background: #dfe4e7; }}
QPushButton#secondary:pressed {{ background: #d7dde1; }}
QPushButton#secondary:disabled {{ background: #eceff1; color: #a0a6ad; }}
QPushButton#primary {{
    background: {ACCENT}; color: #ffffff; border: none;
    padding: 8px 14px; font-weight: bold;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #aeb8b4; }}
QLineEdit {{
    background: {FIELD_BG}; border: 1px solid {BORDER};
    padding: 8px 6px; color: {FIELD_TEXT};
    selection-background-color: {ACCENT}; selection-color: #ffffff;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QComboBox {{
    background: {FIELD_BG}; border: 1px solid #a8adb2;
    padding: 8px 34px 8px 6px; color: {FIELD_TEXT};
}}
QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 34px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; border: none; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT}; selection-color: #ffffff;
    outline: none;
}}
QListWidget {{
    background: {PANEL}; border: 1px solid {BORDER};
    selection-background-color: #dce9e4; selection-color: #1d332c;
    outline: none;
}}
QListWidget::item {{ padding: 4px 6px; }}
"""


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _icon() -> QIcon:
    return QIcon(str(core.resource_path(core.APP_ICON_ICO_NAME)))


def _pixmap(name: str) -> QPixmap | None:
    """Load a UI image, returning ``None`` when it is missing.

    Mirrors ``CodexConfigApp._load_ui_image``, which swallows the same error
    and lets the caller fall back.
    """
    image = QPixmap(str(core.resource_path(name)))
    return None if image.isNull() else image


def _button(
    text: str, role: str, slot=None, width: int | None = None, ipady: int = 0
) -> QPushButton:
    """Build one of the four button roles used across the app.

    ``ipady`` mirrors ttk's ``ipady``, which Tk applies as 2px of height per
    unit.  The profiles toolbar packs its primary button with ``ipady=2`` while
    the official page packs its own with none, which is why the two come out
    35px and 31px tall in the Tk original.
    """
    button = QPushButton(text)
    button.setObjectName(role)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if width is not None:
        button.setFixedWidth(width)
    if ipady:
        button.setFixedHeight(button.sizeHint().height() + 2 * ipady)
    if slot is not None:
        button.clicked.connect(slot)
    return button


def _tk_label_height(label: QLabel, width: int) -> int:
    """The height ``tk.Label`` would give this word-wrapped label at ``width``.

    A single-line role gets its height from the stylesheet padding (see the
    ``QLabel`` rules in ``APP_QSS``), but a wrapped label's height depends on how
    many lines the text takes, and that cannot be expressed in a stylesheet.

    Tk lays a line out at ``font.metrics('linespace')`` and pads the box by 6px.
    Tk's linespace measures ``QFontMetrics.lineSpacing() + 2`` at every size this
    app uses, so the same formula works here.  The line count has to come from
    ``boundingRect`` rather than from ``heightForWidth``: the stylesheet's
    ``padding: 4px 0`` is already inside the latter, so dividing it by the font
    height rounds up and the label is given a phantom extra line.
    (11pt bold is the one size where the two toolkits agree; nothing wrapped uses
    it.)
    """
    metrics = label.fontMetrics()
    wrapped = metrics.boundingRect(
        QRect(0, 0, width, 0), int(Qt.TextFlag.TextWordWrap), label.text()
    )
    lines = max(1, round(wrapped.height() / metrics.height()))
    return (metrics.lineSpacing() + 2) * lines + 6


def _pin_height(widget: QWidget) -> None:
    """Give a single-line label its natural height so a row cannot stretch it.

    Tk's packer never stretches a ``tk.Label`` - its box is always the requested
    height - while Qt's layouts happily stretch one to the row's.  The glyphs
    stay centred either way, so this is invisible on screen; but the box is what
    ``compare_layout.py`` measures, and a box 13px taller than Tk's hides real
    drift from that comparison.  Not for wrapped labels: a fixed height would
    clip the second line.
    """
    widget.ensurePolished()
    widget.setFixedHeight(widget.sizeHint().height())


def _apply_dark_titlebar(widget: QWidget) -> None:
    """Match native dialog chrome to the custom dark title bar.

    Port of ``CodexConfigApp._style_dialog_window``; ``DWMWA_USE_IMMERSIVE_DARK_MODE``
    is attribute 20 on current Windows builds.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        dark_mode = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode)
        )
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def _center_on(widget: QWidget, anchor: QWidget, width: int | None = None, height: int | None = None) -> None:
    """Centre ``widget`` over ``anchor``, or over the screen when there is none.

    Port of ``CodexConfigApp.center_window``; ``width``/``height`` override the
    widget's own size hint the way the Tk version does.
    """
    if width is None or height is None:
        hint = widget.sizeHint()
        if width is None:
            width = hint.width()
        if height is None:
            height = hint.height()
    widget.resize(width, height)
    if anchor is not None:
        anchor_rect = QRect(anchor.mapToGlobal(QPoint(0, 0)), anchor.size())
    else:
        screen = QApplication.primaryScreen()
        anchor_rect = screen.availableGeometry() if screen is not None else QRect(0, 0, width, height)
    x = anchor_rect.x() + max((anchor_rect.width() - width) // 2, 0)
    y = anchor_rect.y() + max((anchor_rect.height() - height) // 2, 0)
    widget.move(x, y)


class _Bridge(QObject):
    """Marshals a callable from a worker thread onto the GUI thread.

    Emitting a signal across threads is thread safe; ``QTimer.singleShot`` is
    not, which is why this exists instead of the Tk version's ``after(0, ...)``.
    """

    call = Signal(object)


# --------------------------------------------------------------------------
# Custom widgets
# --------------------------------------------------------------------------


class DotLabel(QWidget):
    """The green status dot in front of the current-configuration heading."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 25)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BRAND_GREEN))
        painter.drawEllipse(3, 9, 6, 6)
        painter.end()


class TitleButton(QAbstractButton):
    """One of the three custom title-bar controls.

    Draws its own background so the close button can hover red while the other
    two hover grey, and so the "about" button can carry the red update dot.
    """

    def __init__(self, kind: str, pixmap: QPixmap | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._pixmap = pixmap
        self._hover = False
        self._dot = False
        self.setFixedSize(42, TITLE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_dot(self, visible: bool) -> None:
        if self._dot != visible:
            self._dot = visible
            self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        if self._hover:
            background = CLOSE_HOVER if self._kind == "close" else TITLEBAR_HOVER
        else:
            background = TITLEBAR
        painter.fillRect(self.rect(), QColor(background))
        if self._pixmap is not None:
            painter.drawPixmap(
                (self.width() - self._pixmap.width()) // 2,
                (self.height() - self._pixmap.height()) // 2,
                self._pixmap,
            )
        if self._kind == "about" and self._dot:
            painter.setBrush(QColor("#e53935"))
            painter.setPen(QPen(QColor(background), 2))
            painter.drawEllipse(27, 7, 8, 8)
        painter.end()


class NavItem(QAbstractButton):
    """One sidebar entry: a 1px accent indicator plus a left-aligned caption."""

    def __init__(self, key: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._text = text
        self._hover = False
        self.setCheckable(True)
        self.setFixedHeight(NAV_ROW_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        selected = self.isChecked()
        if selected:
            background = SIDEBAR_SELECTED
        elif self._hover:
            background = SIDEBAR_HOVER
        else:
            background = SIDEBAR
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(background))
        if selected:
            painter.fillRect(0, 0, NAV_INDICATOR_WIDTH, self.height(), QColor(ACCENT))
        painter.setPen(QColor(TEXT if selected else "#ffffff"))
        font = QFont(FONT_FAMILY, 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            NAV_TEXT_LEFT,
            0,
            self.width() - NAV_TEXT_LEFT,
            self.height(),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._text,
        )
        painter.end()


# ``CodexConfigApp`` never lets ttk draw the 启动默认模型 drop-down.  The
# ``Model.TCombobox`` style is laid out with ``Combobox.textarea`` only (the
# ``Combobox.arrow`` element is dropped outright), the field reserves 34px of
# right padding for an arrow ttk therefore never draws, and a hand-drawn 28x29
# ``tk.Canvas`` is ``place``d inside that reserve::
#
#     place(in_=model_combo, relx=1.0, rely=0.5, anchor="e", x=-1,
#           width=28, height=29)
#     create_line(8, 11, 13, 16, 18, 11, fill="#59616d", width=2,
#                 joinstyle="round")
#     create_rectangle(27, 0, 28, 29, fill="#a8adb2", outline="")
#
# Its background is ``#f7f8f9`` - the field's own colour - so the button reads
# as seamless until you hover it (``#edf0f2``).  A stock ``QComboBox`` instead
# draws a beveled native button: a 1px white top border, a 1px ``#525353``
# bottom border, a filled ``#525353`` triangle, all separated from the field by
# a 1px gutter.  That bevel is the whole of "启动默认模型的下拉按钮，跟之前的也不
# 一样了", and no amount of QSS padding removes it - the arrow has to be painted,
# which means taking the sub-control out of the style's hands.
ARROW_ZONE_WIDTH = 28
ARROW_ZONE_HEIGHT = 29
ARROW_HOVER_BG = "#edf0f2"
ARROW_STROKE = "#59616d"
ARROW_EDGE = "#a8adb2"


class ComboArrowButton(QWidget):
    """The hand-drawn drop-down button Tk ``place``s inside the combo field.

    A plain child widget rather than a ``::down-arrow`` stylesheet image, because
    that is literally what the Tk build does - and because ``image: url(...)``
    would need a PNG on disk (or in a resource bundle) and would be rescaled by
    Qt, losing the 2px round-joined stroke at the sizes involved here.
    """

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo
        self._hover = False
        self.setFixedSize(ARROW_ZONE_WIDTH, ARROW_ZONE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        # ``post_model_dropdown`` calls ``ttk::combobox::Post`` and focuses the
        # field first; ``showPopup`` is the Qt equivalent of the former.
        if event.button() == Qt.MouseButton.LeftButton:
            self._combo.setFocus(Qt.FocusReason.MouseFocusReason)
            self._combo.showPopup()
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(
            self.rect(), QColor(ARROW_HOVER_BG if self._hover else FIELD_BG)
        )
        # Tk's ``create_line(8, 11, 13, 16, 18, 11, width=2, joinstyle="round")``.
        # The points are Tk's, offset by half a pixel: Tk strokes a line centred
        # on the coordinates it is given, Qt strokes one centred on the pixel
        # *corners*, and without the offset the whole chevron lands one row high
        # and one column left.  With it, ``probe_arrow_pixels.py`` shows rows
        # 12-16 of the two arrows identical cell for cell; only Tk's partial top
        # row (3 pixels where the butt caps end) has no Qt counterpart.
        pen = QPen(QColor(ARROW_STROKE))
        pen.setWidth(2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        # ``joinstyle`` is all Tk sets, so its caps stay at the default butt.
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        # Tk's canvas does not antialias either: its chevron is three flat
        # colours (#59616d / #a8adb2 / #f7f8f9) with hard edges.  Leaving Qt's
        # antialiasing on produces a fuzz of blended greys along both legs
        # instead - visually close, but measurably not the same picture, and
        # this probe exists precisely so that "close" can be checked.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(pen)
        painter.drawPolyline(
            QPolygonF([QPointF(8.5, 12.0), QPointF(13.5, 16.5), QPointF(18.5, 12.0)])
        )
        # ``create_rectangle(27, 0, 28, 29)`` - a 1px inner right edge, drawn
        # just inside the field's own border.
        painter.fillRect(27, 0, 1, ARROW_ZONE_HEIGHT, QColor(ARROW_EDGE))
        painter.end()


class ModelComboBox(QComboBox):
    """``QComboBox`` with Tk's hand-drawn drop-down arrow bolted on.

    Used for 启动默认模型 in the profile editor - the only combo in the app.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.arrow = ComboArrowButton(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_arrow()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # The first resize can land before the stylesheet has given the widget
        # its final border/padding box, so place again once it is on screen.
        self._place_arrow()

    def _place_arrow(self) -> None:
        # Measured on the Tk build: in a 317px-wide field the canvas lands at
        # x=288..315, i.e. its right edge is exactly one pixel inside the field's
        # own right edge, which is where the field's 1px border is drawn.  The
        # canvas's own ``create_rectangle(27, 0, 28, 29)`` then supplies the
        # second ``#a8adb2`` column, which is why the field reads as having a
        # heavier right edge than the other three sides.  Vertically it is
        # centred (Tk: y=4 of 35).
        self.arrow.move(
            self.width() - 1 - ARROW_ZONE_WIDTH,
            (self.height() - ARROW_ZONE_HEIGHT) // 2,
        )
        self.arrow.raise_()


class ChannelCard(QFrame):
    """A clickable provider row on the 推荐渠道 page."""

    activated = Signal(str)

    def __init__(self, title: str, url: str, pixmap: QPixmap | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("channelCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url = url
        row = QHBoxLayout(self)
        # Tk packs the text column with ``pady=9`` while the icon carries its own
        # ``pady=10``; the column is the taller of the two, so 9 is what sets the
        # card's height.  Using 10 here made every card 2px too tall.
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)
        icon = QLabel()
        icon.setObjectName("channelIcon")
        # Tk's icon is a 36x36 image in a label that adds a 2px border, so the
        # widget measures 40x40 with the image centred.
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pixmap is not None:
            icon.setPixmap(
                pixmap.scaled(
                    36,
                    36,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        caption = QLabel(title)
        caption.setObjectName("channelTitle")
        address = QLabel(url)
        address.setObjectName("channelUrl")
        column.addWidget(caption)
        column.addWidget(address)
        row.addLayout(column, 1)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit(self._url)
        super().mouseReleaseEvent(event)


class Toast(QLabel):
    """Short-lived non-blocking status message, shown over the status strip."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFont(QFont(FONT_FAMILY, 9))
        self.setStyleSheet(f"color:{TEXT_MUTED}; background:transparent; padding:1px;")
        self.adjustSize()


# --------------------------------------------------------------------------
# Dialogs
# --------------------------------------------------------------------------


class FlatDialog(QDialog):
    """Base class: app styling, app icon, dark native chrome, parent centring."""

    def __init__(self, parent: QWidget | None, title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(_icon())
        self.setModal(True)
        self.setStyleSheet(DIALOG_QSS)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

    def finish(self, anchor: QWidget | None, width: int | None = None, height: int | None = None) -> None:
        self.adjustSize()
        _center_on(self, anchor, width, height)
        _apply_dark_titlebar(self)


class MessageDialog(FlatDialog):
    """Port of ``CodexConfigApp.show_custom_dialog``.

    ``kind`` selects the icon glyph and colour and whether the answer is a
    boolean (``question``) or an acknowledgement (``info``/``error``).
    """

    def __init__(self, parent: QWidget | None, message: str, kind: str = "info") -> None:
        super().__init__(parent, core.APP_NAME)
        self._value = False

        container = QVBoxLayout(self)
        container.setContentsMargins(18, 18, 18, 18)
        container.setSpacing(0)

        content = QHBoxLayout()
        content.setSpacing(14)
        glyph = {"info": "i", "error": "!", "question": "?"}.get(kind, "i")
        icon = QLabel(glyph)
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background:{ACCENT if kind != 'error' else DANGER_TEXT}; color:#ffffff;"
            f"font-family:'Segoe UI'; font-size:14pt; font-weight:bold;"
        )
        content.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(message)
        label.setWordWrap(True)
        label.setMinimumWidth(380)
        label.setMaximumWidth(420)
        content.addWidget(label, 1)
        container.addLayout(content)

        container.addSpacing(18)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        if kind == "question":
            # 是 on the left, 否 on the right - the order Tk produces, and the
            # Windows message-box convention.  Tk packs both with side="right",
            # 否 first, so 否 takes the right edge and 是 lands to its left
            # (measured: 是 x=346, 否 x=427 in a 500px row, 8px apart).  Adding
            # them in the Tk *creation* order here mirrored the pair, because a
            # left-to-right box lays widgets out in the order they are added.
            yes = _button("是", "secondary", lambda: self._close(True), width=64)
            no = _button("否", "secondary", lambda: self._close(False), width=64)
            buttons.addWidget(yes)
            buttons.addWidget(no)
            self._default_yes = True
        else:
            buttons.addWidget(_button("确定", "outline", lambda: self._close(True), width=76))
            self._default_yes = True
        container.addLayout(buttons)

        self.finish(parent, 500, None)
        # The Tk version grows the dialog with the message; 168 is its floor.
        self.setMinimumHeight(168)

    def _close(self, value: bool) -> None:
        self._value = value
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._close(False)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._close(self._default_yes)
            return
        super().keyPressEvent(event)

    def run(self) -> bool:
        self.exec()
        return self._value


class ConfigNameDialog(FlatDialog):
    """Port of ``CodexConfigApp.ask_config_name``."""

    def __init__(
        self,
        parent: QWidget | None,
        config_dir: Path,
        default_name: str,
        description: str,
        rename_path: Path | None = None,
    ) -> None:
        super().__init__(
            parent, "修改配置名称" if rename_path is not None else "保存配置"
        )
        self._config_dir = config_dir
        self._rename_path = rename_path
        self._value: str | None = None

        container = QVBoxLayout(self)
        container.setContentsMargins(18, 18, 18, 18)
        container.setSpacing(0)

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        container.addWidget(description_label)
        container.addSpacing(8)

        caption = QLabel("配置名称：")
        caption.setObjectName("hint")
        container.addWidget(caption)
        container.addSpacing(4)

        self.entry = QLineEdit(default_name)
        container.addWidget(self.entry)
        container.addSpacing(6)

        self.error_label = QLabel("")
        self.error_label.setObjectName("errorText")
        self.error_label.setWordWrap(True)
        self.error_label.setMinimumHeight(18)
        container.addWidget(self.error_label)

        container.addSpacing(16)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(_button("确定", "outline", self._accept, width=76))
        buttons.addWidget(_button("取消", "outline", self.reject, width=76))
        container.addLayout(buttons)

        self.entry.selectAll()
        self.entry.setFocus()
        self.finish(parent, 440, 205)

        # Pre-validate the suggested name exactly as the Tk version does, so a
        # collision is visible before the user types anything.
        if rename_path is None:
            try:
                core.validate_new_backup_name(config_dir, default_name)
            except core.BackupNameError as exc:
                self.error_label.setText(str(exc))

    def _accept(self) -> None:
        try:
            if self._rename_path is None:
                value = core.validate_new_backup_name(self._config_dir, self.entry.text())
            else:
                value = core.validate_backup_name_format(self.entry.text())
                if core.named_backup_records(self._config_dir, value, exclude_path=self._rename_path):
                    raise core.BackupNameConflictError("已存在同名配置，请使用新的配置名称。")
        except core.BackupNameError as exc:
            self.error_label.setText(str(exc))
            self.entry.setFocus()
            return
        self._value = value
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._accept()
            return
        super().keyPressEvent(event)

    def run(self) -> str | None:
        self.exec()
        return self._value


class ScanPickerDialog(FlatDialog):
    """Port of the multiple-results branch of ``CodexConfigApp._finish_scan``."""

    def __init__(self, parent: QWidget | None, found: list[Path]) -> None:
        super().__init__(parent, "选择扫描结果")
        self._value: Path | None = None

        container = QVBoxLayout(self)
        container.setContentsMargins(16, 16, 16, 16)
        container.setSpacing(0)
        container.addWidget(QLabel("扫描到多个可能的 Codex 配置目录，请选择一个："))
        container.addSpacing(8)

        self.list_widget = QListWidget()
        font = QFont("Consolas", 10)
        self.list_widget.setFont(font)
        for item in found:
            self.list_widget.addItem(QListWidgetItem(str(item)))
        self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._accept())
        container.addWidget(self.list_widget, 1)
        container.addSpacing(12)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(_button("使用选中目录", "outline", self._accept, width=120))
        container.addLayout(buttons)

        self.finish(parent, 560, 300)

    def _accept(self) -> None:
        item = self.list_widget.currentItem()
        if item is not None:
            self._value = Path(item.text())
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._accept()
            return
        super().keyPressEvent(event)

    def run(self) -> Path | None:
        self.exec()
        return self._value


class OnboardingDialog(FlatDialog):
    """Port of ``CodexConfigApp.show_onboarding_dialog``."""

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent, core.APP_NAME)
        self.action = "close"

        container = QVBoxLayout(self)
        container.setContentsMargins(18, 18, 18, 18)
        container.setSpacing(0)

        content = QHBoxLayout()
        content.setSpacing(14)
        icon = QLabel("?")
        icon.setFixedSize(26, 26)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background:{ACCENT}; color:#ffffff; font-family:'Segoe UI';"
            "font-size:14pt; font-weight:bold;"
        )
        content.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        message = QLabel("是否打开新手引导？\n\n选择“是”后，将进入新手引导页面。")
        message.setWordWrap(True)
        message.setMinimumWidth(380)
        content.addWidget(message, 1)
        container.addLayout(content)

        container.addSpacing(18)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(_button("不再弹出", "secondary", lambda: self._close("never"), width=88))
        buttons.addStretch(1)
        # Same 是-then-否 order as MessageDialog above, for the same reason: Tk
        # packs 否 to the right edge first, so 是 ends up on its left.
        buttons.addWidget(_button("是", "secondary", lambda: self._close("open"), width=64))
        buttons.addWidget(_button("否", "secondary", lambda: self._close("close"), width=64))
        container.addLayout(buttons)

        self.finish(parent, 500, 168)

    def _close(self, action: str) -> None:
        self.action = action
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._close("close")
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._close("open")
            return
        super().keyPressEvent(event)

    def run(self) -> str:
        self.exec()
        return self.action


class DonationDialog(FlatDialog):
    """Port of ``CodexConfigApp.show_donation_dialog``."""

    def __init__(self, parent: QWidget | None, image: QPixmap | None) -> None:
        super().__init__(parent, "赞赏作者")
        container = QVBoxLayout(self)
        container.setContentsMargins(20, 20, 20, 20)
        container.setSpacing(0)

        heading = QLabel("感谢你的支持")
        heading.setObjectName("aboutTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container.addWidget(heading)
        container.addSpacing(12)

        picture = QLabel()
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setStyleSheet(f"background:{PANEL}; border: 1px solid {BORDER};")
        if image is not None:
            picture.setPixmap(image)
        container.addWidget(picture, 0, Qt.AlignmentFlag.AlignHCenter)

        self.finish(parent)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)


class AboutDialog(FlatDialog):
    """Port of ``CodexConfigApp.show_about_dialog``.

    The update button is bound to whichever action is current: a fresh check
    when no release is known, a browser launch when one is.
    """

    def __init__(self, owner: "CodexConfigWindow") -> None:
        super().__init__(owner, f"关于 {core.APP_NAME}")
        container = QVBoxLayout(self)
        container.setContentsMargins(28, 16, 28, 16)
        container.setSpacing(0)

        mark = QLabel()
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if owner.about_mark_image is not None:
            mark.setPixmap(owner.about_mark_image)
        else:
            mark.setFixedSize(64, 64)
            mark.setStyleSheet("background:#f3f4f7;")
        container.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        container.addSpacing(7)

        title = QLabel(core.APP_NAME)
        title.setObjectName("aboutTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container.addWidget(title)
        container.addSpacing(3)

        details = QHBoxLayout()
        details.setSpacing(24)
        details.addStretch(1)
        version = QLabel(f"版本 {core.APP_VERSION}")
        version.setObjectName("hint")
        author = QLabel(f"作者：{core.AUTHOR_NAME}")
        author.setObjectName("hint")
        details.addWidget(version)
        details.addWidget(author)
        details.addStretch(1)
        container.addLayout(details)
        container.addSpacing(9)

        tagline = QLabel("安全修改 Codex 本地配置的 Windows 桌面工具")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        tagline.setMinimumWidth(500)
        container.addWidget(tagline)
        container.addSpacing(8)

        self.email_label = QLabel(f"联系邮箱：{core.CONTACT_EMAIL}")
        self.email_label.setObjectName("aboutLink")
        self.email_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.email_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.email_label.mouseReleaseEvent = self._copy_email  # type: ignore[method-assign]
        container.addWidget(self.email_label)
        container.addSpacing(5)

        project = QLabel(f"项目地址：{core.PROJECT_URL}")
        project.setObjectName("aboutLink")
        project.setAlignment(Qt.AlignmentFlag.AlignCenter)
        project.setCursor(Qt.CursorShape.PointingHandCursor)
        project.mouseReleaseEvent = lambda _event: webbrowser.open_new_tab(core.PROJECT_URL)  # type: ignore[method-assign]
        container.addWidget(project)
        container.addSpacing(7)

        available_update = owner.available_update
        self.status_label = QLabel(
            f"发现新版本 {available_update.version}" if available_update is not None else ""
        )
        self.status_label.setObjectName("hint")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_button = _button(
            "前往下载" if available_update is not None else "检查更新",
            "outline",
            width=88,
        )
        if available_update is None:
            self.update_button.clicked.connect(
                lambda: owner.start_update_check(
                    manual=True,
                    parent=self,
                    status_label=self.status_label,
                    button=self.update_button,
                )
            )
        else:
            self.update_button.clicked.connect(
                lambda: webbrowser.open_new_tab(available_update.page_url)
            )
        container.addWidget(self.update_button, 0, Qt.AlignmentFlag.AlignHCenter)
        container.addSpacing(5)
        container.addWidget(self.status_label)
        container.addSpacing(5)

        copyright_label = QLabel(f"Copyright © 2026 {core.AUTHOR_NAME}")
        copyright_label.setObjectName("hint")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container.addWidget(copyright_label)

        self.finish(owner, 560, None)

    def _copy_email(self, _event) -> None:
        QApplication.clipboard().setText(core.CONTACT_EMAIL)
        original = self.email_label.text()
        self.email_label.setText("邮箱已复制")
        QTimer.singleShot(1800, lambda: self.email_label.setText(original))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)


class ProfileEditorDialog(FlatDialog):
    """Port of ``CodexConfigApp._show_profile_editor``.

    ``record is None`` creates a new named profile; otherwise the record's
    profile is updated in place.  Either way the saved profile is *not* applied
    to the live config - the user applies it by double-clicking the row, which
    is the behaviour the Tk build documents in the subtitle.
    """

    def __init__(self, owner: "CodexConfigWindow", record=None) -> None:
        super().__init__(owner, "编辑配置" if record is not None else "新增配置")
        self._owner = owner
        self._record = record
        self._fetched_models: list[str] = (
            core.read_owned_model_catalog_models(record.path) if record is not None else []
        )
        self._show_key = False

        config_dir = owner.current_path()
        source = core.read_codex_config(record.path if record is not None else config_dir)
        active_record = core.resolve_active_profile(config_dir)
        configured_active = core.active_profile_path(config_dir)
        pending_active = core.pending_active_profile_path(config_dir)
        self._editing_active = record is not None and any(
            path is not None and core.normalized_path_key(record.path) == core.normalized_path_key(path)
            for path in (
                active_record.path if active_record is not None else None,
                configured_active,
                pending_active,
            )
        )

        container = QVBoxLayout(self)
        container.setContentsMargins(22, 18, 22, 18)
        container.setSpacing(0)

        title = QLabel("编辑配置" if record is not None else "新增配置")
        title.setObjectName("dialogTitle")
        container.addWidget(title)
        container.addSpacing(3)
        subtitle = QLabel(
            "保存后双击应用；OpenAI 原生模型无需获取列表，“获取模型”仅用于第三方 Provider。"
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        container.addWidget(subtitle)
        container.addSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setColumnStretch(1, 1)
        container.addLayout(form)

        self.name_edit = QLineEdit(record.name if record is not None else core.suggested_config_name(source.provider))
        self.name_edit.setMinimumWidth(300)
        self.api_key_edit = QLineEdit(source.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._eye_action = self.api_key_edit.addAction(
            _icon_from(owner.eye_icon), QLineEdit.ActionPosition.TrailingPosition
        )
        self._eye_action.triggered.connect(self._toggle_editor_key)
        self.provider_edit = QLineEdit(source.provider or core.TEMPLATE_PROVIDER_NAME)
        self.base_url_edit = QLineEdit(source.base_url or core.TEMPLATE_BASE_URL)

        rows = (
            ("配置名称", self.name_edit),
            ("API Key", self.api_key_edit),
            ("Provider 显示名称", self.provider_edit),
            ("Base URL", self.base_url_edit),
        )
        for index, (caption, field) in enumerate(rows):
            label = QLabel(caption)
            label.setObjectName("fieldLabel")
            form.addWidget(label, index, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            form.addWidget(field, index, 1, 1, 2)

        model_caption = QLabel("启动默认模型")
        model_caption.setObjectName("fieldLabel")
        form.addWidget(model_caption, 4, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        self.model_combo = ModelComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_combo.setMinimumWidth(260)
        initial_models = list(self._fetched_models)
        current_model = source.model or core.TEMPLATE_MODEL
        if current_model.strip() and current_model.strip() not in initial_models:
            initial_models.insert(0, current_model.strip())
        self.model_combo.addItems(initial_models)
        self.model_combo.setCurrentText(current_model)
        model_row.addWidget(self.model_combo, 1)
        self.fetch_button = _button("获取模型", "secondary", self._fetch_models, width=88)
        model_row.addWidget(self.fetch_button)
        form.addLayout(model_row, 4, 1, 1, 2)

        container.addSpacing(12)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorText")
        self.error_label.setWordWrap(True)
        self.error_label.setMinimumWidth(280)
        footer.addWidget(self.error_label, 1)
        footer.addWidget(
            _button(
                "保存修改" if record is not None else "保存配置",
                "primary",
                self._save,
                width=100,
            )
        )
        footer.addWidget(_button("取消", "outline", self.reject, width=76))
        container.addLayout(footer)

        self.name_edit.selectAll()
        self.name_edit.setFocus()
        # The Tk build used 570x385.  Qt's own preferred height here is 321,
        # which is also its *minimum*, so it would fit with zero slack; keep the
        # original's roomier box rather than sizing to the exact pixel.
        self.finish(owner, 570, 385)

    def _toggle_editor_key(self) -> None:
        self._show_key = not self._show_key
        self.api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if self._show_key else QLineEdit.EchoMode.Password
        )
        self._eye_action.setIcon(_icon_from(self._owner.eye_off_icon if self._show_key else self._owner.eye_icon))

    def _fetch_models(self) -> None:
        """Query the provider's model list off the GUI thread."""
        base_url = self.base_url_edit.text().strip()
        api_key = self.api_key_edit.text()
        self.error_label.setText("正在获取模型...")
        self.fetch_button.setEnabled(False)

        def worker() -> None:
            try:
                models = core.fetch_available_models(base_url, api_key)
                error = None
            except (core.ModelListError, OSError) as exc:
                models = None
                error = str(exc)
            self._owner.post(lambda: self._finish_fetch(models, error))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_fetch(self, models: list[str] | None, error: str | None) -> None:
        self.fetch_button.setEnabled(True)
        if error is not None:
            self.error_label.setText(error)
            return
        self._fetched_models[:] = models or []
        values = list(self._fetched_models)
        current = self.model_combo.currentText().strip()
        if current and current not in values:
            values.insert(0, current)
        self.model_combo.clear()
        self.model_combo.addItems(values)
        if values:
            self.model_combo.setCurrentText(values[0])
        self.error_label.setText(f"已获取 {len(self._fetched_models)} 个模型")

    def _save(self) -> None:
        provider_name = self.provider_edit.text().strip()
        base_url = self.base_url_edit.text().strip()
        model = self.model_combo.currentText().strip()
        if not provider_name:
            self.error_label.setText("Provider 显示名称不能为空。")
            return
        if not base_url:
            self.error_label.setText("Base URL 不能为空。")
            return
        if not base_url.startswith(("http://", "https://")):
            self.error_label.setText("Base URL 需要以 http:// 或 https:// 开头。")
            return
        if not model:
            self.error_label.setText("Model 不能为空。")
            return

        config_dir = self._owner.current_path()
        try:
            if self._record is None:
                saved = core.create_config_profile(
                    config_dir,
                    self.name_edit.text(),
                    self.api_key_edit.text(),
                    provider_name,
                    base_url,
                    model,
                    apply_to_current=False,
                    available_models=self._fetched_models if self._fetched_models else None,
                )
            else:
                saved = core.update_config_profile(
                    config_dir,
                    self._record.path,
                    self.name_edit.text(),
                    self.api_key_edit.text(),
                    provider_name,
                    base_url,
                    model,
                    apply_to_current=False,
                    available_models=self._fetched_models if self._fetched_models else None,
                )
        except (OSError, core.json.JSONDecodeError, core.BackupNameError) as exc:
            self.error_label.setText(str(exc))
            return

        if self._editing_active:
            core.set_active_profile_path(saved.path)
            core.set_pending_active_profile_path(saved.path)
        self._owner.refresh_profiles(saved.path)
        self.accept()
        if self._editing_active:
            self._owner.load_path(config_dir)
            self._owner.notify(f"已保存修改：{saved.name}；请双击该配置应用。", 3000)
            self._owner.show_info(
                f"已保存修改“{saved.name}”。\n\n请双击该配置应用并启动或重启 Codex。"
            )
        else:
            self._owner.notify(f"已保存配置：{saved.name}")
            self._owner.show_info(f"已保存配置“{saved.name}”。")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


def _icon_from(pixmap: QPixmap | None) -> QIcon:
    return QIcon() if pixmap is None else QIcon(pixmap)


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------


class CodexConfigWindow(QWidget):
    """The Qt main window.

    Constructed exactly like the reference Qt app in this workspace
    (``FramelessWindowHint | Window``, no parent) because that construction is
    what was measured to restore without a blank frame.  Everything inside it
    is a Qt widget, so the window owns one surface and one backing store.
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint,
        )
        self.setObjectName("shell")
        # A plain QWidget does not paint a style-sheet background unless asked;
        # QFrame does, which is why the page containers are frames.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(core.APP_NAME)
        self.setWindowIcon(_icon())
        self.setFixedSize(core.WINDOW_WIDTH, core.WINDOW_HEIGHT)

        # -- state mirrored from CodexConfigApp.__init__ -------------------
        self._path: Path = Path.home() / ".codex"
        self.provider_var = core.DEFAULT_PROVIDER
        self.base_url_var = core.DEFAULT_BASE_URL
        self.model_var = core.TEMPLATE_MODEL
        self.api_key_var = ""
        self.model_display_name_var = ""
        self._show_key = False
        self._update_check_in_progress = False
        self.available_update: core.UpdateInfo | None = None
        self.profile_sort_desc = False
        self.profile_switch_in_progress = False
        self.active_page = "current"
        self.pages: dict[str, QWidget] = {}
        self.nav_items: dict[str, NavItem] = {}
        self._row_records: list[core.BackupRecord] = []
        self.profile_multi_mode = False
        self._toast: Toast | None = None
        self._window_hwnd = 0
        self._taskbar_button_ready = False
        self._drag_origin: QPoint | None = None
        self._drag_window_origin: QPoint | None = None

        self._bridge = _Bridge()
        self._bridge.call.connect(self._run_on_gui_thread)

        # -- images --------------------------------------------------------
        self.app_icon_image = _pixmap(core.APP_ICON_PNG_NAME)
        self.title_icon_image = _pixmap(core.TITLE_ICON_PNG_NAME)
        self.title_button_images = {
            "about": _pixmap(core.TITLE_ABOUT_ICON_NAME),
            "minimize": _pixmap(core.TITLE_MINIMIZE_ICON_NAME),
            "close": _pixmap(core.TITLE_CLOSE_ICON_NAME),
        }
        self.eye_icon = _pixmap(core.EYE_ICON_NAME)
        self.eye_off_icon = _pixmap(core.EYE_OFF_ICON_NAME)
        self.about_mark_image = _pixmap(core.ABOUT_MARK_PNG_NAME)
        self.arkapi_icon_image = _pixmap(core.ARKAPI_ICON_NAME)
        self.jm2api_icon_image = _pixmap(core.JM2API_ICON_NAME)
        self.donation_thumbnail = _pixmap(core.DONATION_THUMBNAIL_IMAGE_NAME)
        self.donation_dialog_image = _pixmap(core.DONATION_DIALOG_IMAGE_NAME)

        self._build_ui()
        self._center_main_window()
        self._load_initial_path()

        QTimer.singleShot(50, self._set_appwindow_style)
        QTimer.singleShot(150, self.show_onboarding_dialog)
        QTimer.singleShot(1200, self.check_for_updates_on_startup)

    # -- threading glue ----------------------------------------------------

    def post(self, callback) -> None:
        """Schedule ``callback`` on the GUI thread from any thread."""
        self._bridge.call.emit(callback)

    def _run_on_gui_thread(self, callback) -> None:
        try:
            callback()
        except RuntimeError:
            # The window is gone; a late worker result has nowhere to land.
            pass

    # -- layout ------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_title_bar())

        body = QFrame()
        body.setObjectName("pageHost")
        body_row = QHBoxLayout(body)
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(self._build_sidebar())

        host = QFrame()
        host.setObjectName("pageHost")
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        self.page_host = QStackedWidget()
        host_layout.addWidget(self.page_host)
        body_row.addWidget(host, 1)
        root.addWidget(body, 1)

        self._build_current_page()
        self._build_profiles_page()
        self._build_official_page()
        self._build_guide_page()
        self._build_recommended_page()
        self.show_page("current")

    def _build_title_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(TITLE_HEIGHT)
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 0, 0, 0)
        row.setSpacing(0)

        self.title_icon_label = QLabel()
        if self.title_icon_image is not None:
            self.title_icon_label.setPixmap(self.title_icon_image)
        self.title_icon_label.setFixedHeight(TITLE_HEIGHT)
        row.addWidget(self.title_icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        row.addSpacing(7)
        self.title_label = QLabel(core.APP_NAME)
        self.title_label.setObjectName("titleText")
        row.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

        self.about_button = TitleButton("about", self.title_button_images["about"])
        self.about_button.setToolTip("关于软件")
        self.about_button.clicked.connect(self.show_about_dialog)
        self.minimize_button = TitleButton("minimize", self.title_button_images["minimize"])
        self.minimize_button.clicked.connect(self._minimize_window)
        self.close_button = TitleButton("close", self.title_button_images["close"])
        self.close_button.clicked.connect(self.close)

        # Tk packs all three with side="right", and Tk hands the *right edge* to
        # the first widget packed - so the Tk order close, minimise, about
        # renders left-to-right as about / minimise / close.  QHBoxLayout
        # appends left-to-right instead, so feeding it the Tk *pack* order puts
        # close on the left and about on the right.  Add them in visual order.
        for button in (self.about_button, self.minimize_button, self.close_button):
            row.addWidget(button)

        # Anywhere on the black strip drags the window.
        for widget in (bar, self.title_icon_label, self.title_label):
            widget.installEventFilter(self)
        return bar

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        column = QVBoxLayout(sidebar)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addSpacing(26)

        self._nav_group = QWidget()
        nav_layout = QVBoxLayout(self._nav_group)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        for key, text in (
            ("current", "当前配置"),
            ("profiles", "切换配置"),
            ("official", "官方登录"),
            ("guide", "新手引导"),
            ("recommended", "推荐渠道"),
        ):
            item = NavItem(key, text)
            item.clicked.connect(lambda _checked=False, target=key: self.show_page(target))
            nav_layout.addWidget(item)
            self.nav_items[key] = item
        column.addWidget(self._nav_group)
        column.addStretch(1)

        if self.donation_thumbnail is not None:
            donation = QToolButton()
            donation.setCursor(Qt.CursorShape.PointingHandCursor)
            donation.setToolTip("赞赏作者")
            donation.setIcon(QIcon(self.donation_thumbnail))
            donation.setIconSize(self.donation_thumbnail.size())
            donation.setFixedSize(self.donation_thumbnail.size())
            donation.setStyleSheet("QToolButton { border: none; background: transparent; }")
            donation.clicked.connect(self.show_donation_dialog)
            column.addWidget(donation, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(15)
        return sidebar

    def _new_page(self, key: str) -> tuple[QFrame, QVBoxLayout]:
        page = QFrame()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.page_host.addWidget(page)
        self.pages[key] = page
        return page, layout

    @staticmethod
    def _page_header(layout: QVBoxLayout, title: str, subtitle: str = "") -> QVBoxLayout:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(28, 16, 28, 11)
        column.setSpacing(0)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        column.addWidget(heading)
        if subtitle:
            column.addSpacing(4)
            note = QLabel(subtitle)
            note.setObjectName("pageSubtitle")
            note.setWordWrap(True)
            column.addWidget(note)
        layout.addWidget(holder)
        return column

    @staticmethod
    def _panel(
        layout: QVBoxLayout,
        padding: tuple[int, int] = (14, 12),
        expand: bool = False,
        margins: tuple[int, int, int, int] = (28, 0, 28, 12),
    ) -> QVBoxLayout:
        """A white bordered panel, inset 28px like ``CodexConfigApp._panel``.

        Returns the panel's *inner* layout; callers add their own rows to it.
        ``expand`` is for the one panel that fills the page (推荐渠道).
        """
        holder = QFrame()
        holder_row = QVBoxLayout(holder)
        holder_row.setContentsMargins(*margins)
        holder_row.setSpacing(0)
        outer = QFrame()
        outer.setObjectName("panel")
        # The padding-carrying layout goes straight onto the bordered frame.
        # It used to sit on a nested QWidget inside a second layout, and that
        # extra QWidget stopped the panel from ever asking its children for a
        # heightForWidth - so a word-wrapped QLabel was given a one-line height
        # and its second line was silently clipped.
        inner_layout = QVBoxLayout(outer)
        inner_layout.setContentsMargins(padding[0], padding[1], padding[0], padding[1])
        inner_layout.setSpacing(0)
        # Vertical policy stays growable.  A Fixed policy pins the panel to its
        # sizeHint height, which is the same trap.  The pages no longer need
        # Fixed to stop a panel absorbing slack: they end with ``_pack_top``,
        # which puts the slack below the content instead.
        outer.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred if expand else QSizePolicy.Policy.Minimum,
        )
        holder_row.addWidget(outer)
        layout.addWidget(holder, 1 if expand else 0)
        return inner_layout

    @staticmethod
    def _pack_top(layout: QVBoxLayout) -> None:
        """Leave the page's slack at the *bottom*, the way Tk's ``pack`` does.

        Tk gives every ``pack(fill="x")`` widget its natural height and leaves
        the remaining space empty below the last one.  ``QVBoxLayout`` instead
        spreads slack across every item that can grow, so the header stretches
        and a gap opens between it and the first panel - which is exactly how
        the 官方登录 / 新手引导 / 当前配置 pages drifted away from the Tk design
        while still passing every structural test.

        A trailing stretch reproduces ``pack``: the items keep their size hints
        and the slack collects at the bottom.  Call this at the end of any page
        whose content does **not** expand - do not call it on 切换配置 (its
        table fills the page) or 推荐渠道 (its panel carries the stretch).
        """
        layout.addStretch(1)

    def _build_current_page(self) -> None:
        page, layout = self._new_page("current")

        header = QWidget()
        header_column = QVBoxLayout(header)
        header_column.setContentsMargins(28, 16, 28, 11)
        header_column.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setSpacing(0)
        title_row.addWidget(DotLabel(), 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addSpacing(5)
        self.current_name_label = QLabel("未保存配置")
        self.current_name_label.setObjectName("currentName")
        title_row.addWidget(self.current_name_label)
        title_row.addStretch(1)
        header_column.addLayout(title_row)

        welcome = QLabel("欢迎使用Codex配置助手，如果觉得软件好用，请点击左侧二维码并扫描，支持作者。")
        welcome.setObjectName("pageSubtitle")
        header_column.addSpacing(4)
        header_column.addWidget(welcome)
        layout.addWidget(header)

        # -- path panel ----------------------------------------------------
        path_holder = self._panel(layout, (12, 9))
        caption = QLabel("Codex 配置目录")
        caption.setObjectName("panelHeading")
        path_holder.addWidget(caption)
        path_holder.addSpacing(6)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(_button("浏览...", "secondary", self.choose_path, width=88))
        # Wrapped, not passed directly: QPushButton.clicked carries a ``checked``
        # bool, which would arrive as ``record`` and make the editor treat it as
        # an existing record (``record.path`` on a bool).
        path_row.addWidget(_button("新增配置", "secondary", lambda: self._show_profile_editor(), width=95))
        path_holder.addLayout(path_row)

        # -- details panel -------------------------------------------------
        details = self._panel(layout, (16, 8))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        # Tk grids every row with pady=6, so the first and last row carry the
        # padding too.  QGridLayout's verticalSpacing only sits *between* rows;
        # without this the panel comes out 12px shorter than the Tk original.
        grid.setContentsMargins(0, 6, 0, 6)
        grid.setColumnStretch(1, 1)
        details.addLayout(grid)

        self.key_entry = self._readonly_field(grid, 0, "API Key", "", secret=True)
        self.provider_field = self._readonly_field(grid, 1, "Provider 显示名称", self.provider_var)
        self.base_url_field = self._readonly_field(grid, 2, "Base URL", self.base_url_var)
        self.model_field = self._readonly_field(grid, 3, "启动默认模型", self.model_var)

        self._pack_top(layout)

    def _readonly_field(
        self,
        grid: QGridLayout,
        row: int,
        label: str,
        value: str,
        secret: bool = False,
    ) -> QLineEdit:
        caption = QLabel(label)
        caption.setObjectName("fieldLabel")
        grid.addWidget(caption, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        entry = QLineEdit(value)
        entry.setReadOnly(True)
        if secret:
            entry.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_action = entry.addAction(
                _icon_from(self.eye_icon), QLineEdit.ActionPosition.TrailingPosition
            )
            self._eye_action.triggered.connect(self.toggle_key_visibility)
        grid.addWidget(entry, row, 1)
        return entry

    def _build_profiles_page(self) -> None:
        page, layout = self._new_page("profiles")
        self._page_header(
            layout,
            "已保存配置",
            "双击目标配置，软件会保存当前公开设置、切换配置并自动启动 Codex。",
        )

        toolbar = QWidget()
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(28, 0, 28, 10)
        toolbar_row.setSpacing(8)
        toolbar_row.addWidget(_button("打开配置库目录", "secondary", self.open_backup_dir))
        toolbar_row.addWidget(_button("新增配置", "secondary", lambda: self._show_profile_editor()))
        toolbar_row.addStretch(1)
        search_caption = QLabel("搜索")
        search_caption.setObjectName("hint")
        _pin_height(search_caption)
        toolbar_row.addWidget(search_caption)
        self.profile_search_edit = QLineEdit()
        self.profile_search_edit.setObjectName("searchField")
        self.profile_search_edit.setFixedWidth(180)
        self.profile_search_edit.textChanged.connect(lambda _text: self.refresh_profiles())
        toolbar_row.addWidget(self.profile_search_edit)
        self.profile_switch_button = _button(
            "切换到该配置", "primary", self._switch_selected_profile, ipady=2
        )
        toolbar_row.addWidget(self.profile_switch_button)
        layout.addWidget(toolbar)

        self.profile_empty_label = QLabel("")
        self.profile_empty_label.setObjectName("hint")
        self.profile_empty_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        empty_holder = QWidget()
        empty_row = QHBoxLayout(empty_holder)
        empty_row.setContentsMargins(28, 0, 28, 6)
        empty_row.addWidget(self.profile_empty_label)
        layout.addWidget(empty_holder)

        table_panel = QFrame()
        table_panel.setObjectName("treePanel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_table = QTableWidget(0, 2)
        self.profile_table.setHorizontalHeaderLabels(["配置名称  ▲", "Base URL"])
        self.profile_table.verticalHeader().setVisible(False)
        self.profile_table.verticalHeader().setDefaultSectionSize(31)
        self.profile_table.setShowGrid(False)
        self.profile_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.profile_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.profile_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.profile_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.profile_table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionsClickable(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Tk configures ``name`` at 225 and ``base_url`` at 330 in a 608px-wide
        # ``Treeview``, but ttk's ``stretch`` defaults to true on *every* column,
        # so the 53px of slack is split between them and ``name`` ends up ~251px
        # wide - which is where the header's divider actually lands.
        # Qt has no equivalent mode: ``Stretch`` splits evenly and ignores the
        # configured widths (measured: 310/310), and ``Interactive + Stretch``
        # hands column 1 all of the slack (225/395).  ``probe_column_widths.py``
        # is that measurement.  The window is fixed at 820x500, so the view width
        # is constant and ttk's rule collapses to a number: 225 + 53 // 2.
        # Plus 2, because the section's 3px ``border-right`` is drawn *inside*
        # the section - Tk's divider sits at x=421..423 and the border has to be
        # pushed right to get there rather than eating into the column.
        self.profile_table.setColumnWidth(0, 251 + 2)
        header.sectionClicked.connect(self._on_profile_header_clicked)
        self.profile_table.itemSelectionChanged.connect(self._update_profile_buttons)
        self.profile_table.cellDoubleClicked.connect(lambda _row, _col: self._profile_double_click())
        self.profile_table.customContextMenuRequested.connect(self._show_profile_context_menu)
        table_layout.addWidget(self.profile_table)

        table_holder = QWidget()
        table_holder_row = QVBoxLayout(table_holder)
        table_holder_row.setContentsMargins(28, 0, 28, core.STATUS_AREA_HEIGHT)
        table_holder_row.addWidget(table_panel)
        layout.addWidget(table_holder, 1)

        self.profile_multi_bar = QWidget()
        multi_row = QHBoxLayout(self.profile_multi_bar)
        multi_row.setContentsMargins(28, 0, 28, 8)
        multi_row.setSpacing(8)
        self.profile_select_all_button = _button("全选", "outline", self._toggle_profile_select_all)
        multi_row.addWidget(self.profile_select_all_button)
        self.profile_delete_selected_button = _button(
            "删除所选配置", "danger", lambda: self._delete_profile_records(self._selected_profile_records())
        )
        multi_row.addWidget(self.profile_delete_selected_button)
        multi_row.addStretch(1)
        multi_row.addWidget(_button("退出多选", "outline", lambda: self._set_profile_multi_mode(False)))
        layout.addWidget(self.profile_multi_bar)

        self._set_profile_multi_mode(False)

    def _build_official_page(self) -> None:
        page, layout = self._new_page("official")
        self._page_header(
            layout, "官方登录", "切换到 Codex 官方登录配置，用自己的 ChatGPT/GPT 账号登录。"
        )
        panel = self._panel(layout, (20, 18))
        self.official_status_label = QLabel("当前未使用官方登录模式")
        self.official_status_label.setObjectName("bigStatus")
        panel.addWidget(self.official_status_label)
        panel.addSpacing(12)
        description = QLabel("切换后不会丢失聊天记录，已保存的 API 配置也会保留。")
        description.setObjectName("bodyText")
        description.setWordWrap(True)
        panel.addWidget(description)
        panel.addSpacing(18)
        self.official_action_button = _button(
            "进入官方登录模式", "primary", self.restore_defaults
        )
        panel.addWidget(self.official_action_button, 0, Qt.AlignmentFlag.AlignLeft)
        self._pack_top(layout)

    def _build_guide_page(self) -> None:
        page, layout = self._new_page("guide")
        self._page_header(layout, "新手引导", "配置助手主要提供新增配置和切换配置两个功能。")
        panel = self._panel(layout, (20, 15))
        important_model_hint = "供应商是GPT或者OpenAI模型时，无需获取模型"
        sections = (
            (
                "新增配置",
                (
                    "打开“新增配置”，填写配置名称、API Key、Provider 显示名称、Base URL 和启动默认模型。",
                    important_model_hint,
                ),
            ),
            (
                "切换配置",
                (
                    "双击目标配置即可应用并启动 Codex；运行中切换时需确认自动重启。",
                    "编辑正在使用的配置后，也需要双击该配置应用修改。",
                ),
            ),
        )
        for title, messages in sections:
            heading = QLabel(title)
            heading.setObjectName("sectionTitle")
            panel.addWidget(heading)
            panel.addSpacing(6)
            for message in messages:
                bullet = QLabel("• " + message)
                bullet.setObjectName(
                    "bodyTextWarn" if message == important_model_hint else "bodyText"
                )
                bullet.setWordWrap(True)
                # Tk sets wraplength=500 here.  Constraining the width is not
                # enough on its own: QLabel reports a word-wrapped height only
                # through heightForWidth(), and the panel layouts in between
                # hand it a one-line height from sizeHint() - so the second line
                # is clipped rather than wrapped.  Pin the height Tk would have
                # given it.  (The app stylesheet is already installed by
                # create_application(), so the font is resolved here.)
                bullet.setFixedWidth(500)
                bullet.ensurePolished()
                bullet.setFixedHeight(_tk_label_height(bullet, 500))
                panel.addWidget(bullet)
                panel.addSpacing(7)
            separator = QFrame()
            separator.setObjectName("separator")
            separator.setFixedHeight(1)
            # Tk packs the separator with pady=(3, 14) after *every* section,
            # the last one included.  Skipping the trailing 14px on the final
            # section left the panel 14px shorter than the Tk original.
            panel.addSpacing(3)
            panel.addWidget(separator)
            panel.addSpacing(14)

        self._pack_top(layout)

    def _build_recommended_page(self) -> None:
        page, layout = self._new_page("recommended")
        self._page_header(layout, "推荐渠道", "精选 API 服务渠道。")

        outer = QFrame()
        outer.setObjectName("panel")
        inner = QWidget()
        column = QVBoxLayout(inner)
        column.setContentsMargins(20, 15, 20, 15)
        column.setSpacing(10)
        for title, url, image in (
            (
                "AI Ark API    更高性价比    快速稳定    隐私安全    价格透明",
                core.RECOMMENDED_CHANNEL_URL,
                self.arkapi_icon_image,
            ),
            ("JM2 API", core.JM2API_CHANNEL_URL, self.jm2api_icon_image),
        ):
            card = ChannelCard(title, url, image)
            card.activated.connect(lambda target: webbrowser.open(target, new=2))
            column.addWidget(card)
        column.addStretch(1)
        shell = QVBoxLayout(outer)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.addWidget(inner)

        holder = QWidget()
        holder_row = QVBoxLayout(holder)
        holder_row.setContentsMargins(28, 0, 28, 28)
        holder_row.addWidget(outer)
        layout.addWidget(holder, 1)

    def _center_main_window(self) -> None:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
        x = available.x() + max((available.width() - core.WINDOW_WIDTH) // 2, 0)
        y = available.y() + max((available.height() - core.WINDOW_HEIGHT) // 2, 0)
        self.move(x, y)

    # -- window management -------------------------------------------------

    def eventFilter(self, watched, event) -> bool:
        """Let the title strip start a system move.

        ``startSystemMove`` hands the drag to the window manager, which is what
        keeps the drag smooth and gives snap/aero-shake for free.  The manual
        path below it is only a fallback for platforms that refuse.
        """
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None and handle.startSystemMove():
                return True
            self._drag_origin = event.globalPosition().toPoint()
            self._drag_window_origin = self.frameGeometry().topLeft()
            return True
        if event.type() == QEvent.Type.MouseMove and self._drag_origin is not None:
            delta = event.globalPosition().toPoint() - self._drag_origin
            self.move(self._drag_window_origin + delta)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            self._drag_origin = None
            self._drag_window_origin = None
        return super().eventFilter(watched, event)

    def _minimize_window(self) -> None:
        """Minimise through Qt, which keeps the taskbar button and the style.

        The Tk build had to ask the OS directly because ``iconify`` is a no-op
        for an ``overrideredirect`` window; a Qt top level has no such problem.
        """
        self.showMinimized()

    # WM_SYSCOMMAND / SC_MAXIMIZE, masked the way Windows documents it: the low
    # four bits of the command are reserved for the system.
    _WM_SYSCOMMAND = 0x0112
    _SC_MAXIMIZE = 0xF030
    _SC_COMMAND_MASK = 0xFFF0

    def nativeEvent(self, event_type, message):
        """Refuse ``SC_MAXIMIZE`` so the window can only be minimised.

        Leaving ``WS_MAXIMIZEBOX`` unset removes the shell's maximise button and
        the system-menu entry, but ``DefWindowProc`` honours
        ``WM_SYSCOMMAND``/``SC_MAXIMIZE`` whatever the style says - and that is
        the path Win+Up takes.  Measured on both front ends with
        ``prototypes/probe_sc_maximize.py``: a synthetic ``SC_MAXIMIZE`` resizes
        the Tk build to 1920x1080 and an unguarded Qt window to 1920x1040, so
        the style bits alone do not implement the requirement.

        Dropping the command here does, without touching the style bits or any
        taskbar behaviour - and this is the one requirement the port implements
        more strictly than the build it replaces.
        """
        if os.name == "nt":
            msg = None
            try:
                import ctypes.wintypes

                msg = ctypes.wintypes.MSG.from_address(int(message))
            except (AttributeError, TypeError, ValueError):
                msg = None
            if (
                msg is not None
                and msg.message == self._WM_SYSCOMMAND
                and (msg.wParam & self._SC_COMMAND_MASK) == self._SC_MAXIMIZE
            ):
                return True, 0
        return super().nativeEvent(event_type, message)

    def resizeEvent(self, event) -> None:
        """Snap back to 820x500 if anything resizes the window behind Qt's back.

        Three guards implement "minimise only": ``WS_MAXIMIZEBOX`` is unset (no
        button, no menu entry), ``nativeEvent`` drops ``SC_MAXIMIZE`` (the Win+Up
        path), and this catches the rest.  A direct
        ``ShowWindow(SW_SHOWMAXIMIZED)`` sets ``WS_MAXIMIZE`` and resizes the
        window without going through either of those, and because Qt's own
        ``windowState()`` stays ``WindowNoState`` - measured - neither
        ``changeEvent`` nor ``showNormal()`` does anything about it.

        ``setFixedSize`` pins the minimum and maximum to the same value, so Qt
        itself can never deliver a resize to another size.  A resize to anything
        else can only have come from outside, which is why reverting is safe.
        Deferred, so the resize is not re-entered from inside its own handler.
        """
        super().resizeEvent(event)
        if self.width() == core.WINDOW_WIDTH and self.height() == core.WINDOW_HEIGHT:
            return
        # A minimised window reports the shell's 160x28 icon-sized client rect,
        # so this fires on every minimise.  Leaving it alone matters: acting on
        # it would try to resize a minimised window, which is how a "stay
        # minimised" requirement gets broken by a maximise guard.
        if self.isMinimized():
            return
        QTimer.singleShot(0, self._undo_external_resize)

    _SW_RESTORE = 9

    def _undo_external_resize(self) -> None:
        """Clear an externally-set maximised state and go back to 820x500.

        ``SW_RESTORE`` rather than ``showNormal()``: Qt's ``windowState()`` never
        changed, so it believes the window is already normal and its own
        ``showNormal()`` is a no-op.  ``SW_RESTORE`` is what actually clears
        ``WS_MAXIMIZE``, and it puts the window back at its restore rectangle.
        """
        hwnd = self._window_handle()
        if hwnd:
            try:
                import ctypes

                user32 = ctypes.windll.user32
                if user32.IsZoomed(hwnd):
                    user32.ShowWindow(hwnd, self._SW_RESTORE)
            except (AttributeError, OSError):
                pass
        self.resize(core.WINDOW_WIDTH, core.WINDOW_HEIGHT)

    def _window_handle(self) -> int:
        if os.name != "nt":
            return 0
        if self._window_hwnd:
            return self._window_hwnd
        try:
            self._window_hwnd = int(self.winId())
        except (RuntimeError, TypeError, ValueError):
            self._window_hwnd = 0
        return self._window_hwnd

    def _set_appwindow_style(self, attempt: int = 0) -> None:
        """Register with the shell and make sure the taskbar button exists."""
        if os.name != "nt":
            return
        hwnd = self._window_handle()
        if not hwnd:
            if attempt < 5:
                QTimer.singleShot(200, lambda: self._set_appwindow_style(attempt + 1))
            return
        try:
            import ctypes

            core.register_appwindow_with_shell(hwnd, ctypes.windll.user32)
            core.make_window_minimizable(hwnd, ctypes.windll.user32)
        except (AttributeError, OSError):
            pass
        self._taskbar_button_ready = core.ensure_taskbar_button(hwnd)
        if not self._taskbar_button_ready and attempt < 5:
            QTimer.singleShot(300, lambda: self._set_appwindow_style(attempt + 1))

    def changeEvent(self, event) -> None:
        """Undo any maximise, and re-assert the minimisable style.

        Port of the Tk build's ``<Map>`` handler: a state change is the moment
        the style bits can be dropped, so they are re-applied rather than
        assumed to have survived.

        The maximise revert covers the paths that set ``WS_MAXIMIZE`` directly
        instead of going through a command - an explicit
        ``ShowWindow(SW_MAXIMIZE)``, for instance - which ``nativeEvent`` cannot
        intercept.  The window is fixed at 820x500, so a maximised state is
        always wrong.  Deferred, because re-entering a state change from inside
        its own handler is exactly the kind of thing Qt warns about.
        """
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange:
            return
        if self.windowState() & Qt.WindowState.WindowMaximized:
            QTimer.singleShot(0, self.showNormal)
        if os.name != "nt":
            return
        hwnd = self._window_handle()
        if hwnd:
            try:
                import ctypes

                core.make_window_minimizable(hwnd, ctypes.windll.user32)
            except (AttributeError, OSError):
                pass
        if not self._taskbar_button_ready:
            QTimer.singleShot(50, self._set_appwindow_style)

    # -- page navigation ---------------------------------------------------

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.active_page = key
        self.page_host.setCurrentWidget(page)
        for item_key, item in self.nav_items.items():
            item.setChecked(item_key == key)
        if key == "profiles":
            self.refresh_profiles()
        elif key == "official":
            self._refresh_official_page()

    # -- notifications -----------------------------------------------------

    def notify(self, message: str, duration: int = 1800) -> None:
        """Port of ``CodexConfigApp._notify``: a toast over the status strip."""
        if self._toast is not None:
            self._toast.close()
            self._toast = None
        toast = Toast(message)
        content_left = SIDEBAR_WIDTH
        content_width = self.width() - content_left
        x = self.x() + content_left + max((content_width - toast.width()) // 2, 8)
        status_top = self.y() + self.height() - core.STATUS_AREA_HEIGHT
        y = status_top + max((core.STATUS_AREA_HEIGHT - toast.height()) // 2, 0)
        toast.move(x, y)
        toast.show()
        self._toast = toast
        QTimer.singleShot(duration, toast.close)

    def show_error(self, message: str, parent: QWidget | None = None) -> None:
        MessageDialog(parent or self, message, kind="error").run()

    def show_info(self, message: str, parent: QWidget | None = None) -> None:
        MessageDialog(parent or self, message, kind="info").run()

    def ask_yes_no(self, message: str, parent: QWidget | None = None) -> bool:
        return MessageDialog(parent or self, message, kind="question").run()

    # -- update check ------------------------------------------------------

    def _set_available_update(self, update: core.UpdateInfo | None) -> None:
        self.available_update = update
        self.about_button.set_dot(update is not None)

    def check_for_updates_on_startup(self) -> None:
        self.start_update_check(manual=False)

    def start_update_check(
        self,
        manual: bool,
        parent: QWidget | None = None,
        status_label: QLabel | None = None,
        button: QPushButton | None = None,
    ) -> None:
        if self._update_check_in_progress:
            if status_label is not None:
                status_label.setText("正在检查更新...")
            if button is not None:
                button.setEnabled(False)
            QTimer.singleShot(
                400,
                lambda: self.start_update_check(manual, parent, status_label, button)
                if parent is None or parent.isVisible()
                else None,
            )
            return
        self._update_check_in_progress = True
        if status_label is not None:
            status_label.setText("正在检查更新...")
        if button is not None:
            button.setEnabled(False)

        def worker() -> None:
            try:
                update = core.fetch_latest_release()
                error = None
            except core.UpdateCheckError as exc:
                update = None
                error = str(exc)
            except Exception:
                update = None
                error = "检查更新时发生未知错误。"
            self.post(
                lambda: self._finish_update_check(manual, status_label, button, update, error)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check(
        self,
        manual: bool,
        status_label: QLabel | None,
        button: QPushButton | None,
        update: core.UpdateInfo | None,
        error: str | None,
    ) -> None:
        self._update_check_in_progress = False
        if button is not None:
            try:
                button.setEnabled(True)
            except RuntimeError:
                button = None
        if error is not None:
            if manual and status_label is not None:
                status_label.setText(error)
            return
        if update is None:
            self._set_available_update(None)
            if manual and status_label is not None:
                status_label.setText(f"当前已是最新版本 {core.APP_VERSION}")
            return
        self._set_available_update(update)
        if status_label is not None:
            status_label.setText(f"发现新版本 {update.version}")
        if button is not None:
            button.setText("前往下载")
            try:
                button.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            button.clicked.connect(lambda: webbrowser.open_new_tab(update.page_url))

    # -- dialogs -----------------------------------------------------------

    def show_about_dialog(self) -> None:
        AboutDialog(self).exec()

    def show_donation_dialog(self) -> None:
        if self.donation_dialog_image is None:
            self.show_error("赞赏码图片未找到。")
            return
        DonationDialog(self, self.donation_dialog_image).exec()

    def show_onboarding_dialog(self, force: bool = False) -> None:
        settings = core.load_settings()
        if not force and not core.should_show_onboarding(settings):
            return
        action = OnboardingDialog(self).run()
        if action == "never":
            core.save_setting_value(core.HIDE_ONBOARDING_KEY, True)
        if action == "open":
            self.show_page("guide")
        self.raise_()
        self.activateWindow()

    def ask_config_name(
        self,
        config_dir: Path,
        default_name: str,
        description: str,
        parent: QWidget | None = None,
        rename_path: Path | None = None,
    ) -> str | None:
        return ConfigNameDialog(
            parent or self, config_dir, default_name, description, rename_path
        ).run()

    def _show_profile_editor(self, record: core.BackupRecord | None = None) -> None:
        ProfileEditorDialog(self, record).exec()

    # -- profiles ----------------------------------------------------------

    def _selected_profile_records(self) -> list[core.BackupRecord]:
        rows = sorted({index.row() for index in self.profile_table.selectedIndexes()})
        return [
            self._row_records[row]
            for row in rows
            if 0 <= row < len(self._row_records)
        ]

    def refresh_profiles(self, select_path: Path | None = None) -> None:
        if not hasattr(self, "profile_table"):
            return
        previous_paths = {
            core.normalized_path_key(record.path) for record in self._selected_profile_records()
        }
        if select_path is not None:
            previous_paths = {core.normalized_path_key(select_path)}

        active_record = core.find_matching_backup(self.current_path())
        active_key = core.normalized_path_key(active_record.path) if active_record is not None else None
        records = list(core.list_backup_records(self.current_path()))
        records.sort(key=lambda item: item.name.casefold(), reverse=self.profile_sort_desc)
        if active_key:
            records.sort(key=lambda item: core.normalized_path_key(item.path) != active_key)

        query = self.profile_search_edit.text().strip().casefold()
        self._row_records = []
        selected_rows: list[int] = []
        self.profile_table.setUpdatesEnabled(False)
        self.profile_table.clearContents()
        self.profile_table.setRowCount(0)
        for record in records:
            profile_entry = core.cached_profile_entry(record.path)
            if query and query not in record.name.casefold() and query not in profile_entry.base_url.casefold():
                continue
            record_key = core.normalized_path_key(record.path)
            is_active = record_key == active_key
            row = self.profile_table.rowCount()
            self.profile_table.insertRow(row)
            name_item = QTableWidgetItem(f"●  {record.name}" if is_active else record.name)
            if is_active:
                name_item.setForeground(QColor("#218354"))
            url_item = QTableWidgetItem(profile_entry.base_url)
            self.profile_table.setItem(row, 0, name_item)
            self.profile_table.setItem(row, 1, url_item)
            self._row_records.append(record)
            if record_key in previous_paths:
                selected_rows.append(row)
        self.profile_table.setUpdatesEnabled(True)

        if not self._row_records:
            self.profile_empty_label.setText(
                "没有符合条件的配置。" if query else "暂无已保存配置，可以从当前配置页面新增。"
            )
        else:
            self.profile_empty_label.setText(f"共 {len(self._row_records)} 个配置")

        if selected_rows:
            self.profile_table.selectRow(selected_rows[0])
        elif self._row_records and not self.profile_multi_mode:
            self.profile_table.selectRow(0)
        self._update_profile_buttons()

    def _on_profile_header_clicked(self, section: int) -> None:
        if section != 0:
            return
        self.profile_sort_desc = not self.profile_sort_desc
        self.profile_table.horizontalHeaderItem(0).setText(
            "配置名称  ▼" if self.profile_sort_desc else "配置名称  ▲"
        )
        self.refresh_profiles()

    def _update_profile_buttons(self) -> None:
        if not hasattr(self, "profile_table"):
            return
        selection_count = len(self._selected_profile_records())
        item_count = len(self._row_records)
        self.profile_switch_button.setEnabled(selection_count == 1 and not self.profile_multi_mode)
        self.profile_delete_selected_button.setEnabled(bool(selection_count))
        self.profile_select_all_button.setText(
            "取消全选" if item_count and selection_count == item_count else "全选"
        )
        self.profile_select_all_button.setEnabled(bool(item_count))

    def _set_profile_multi_mode(self, enabled: bool) -> None:
        self.profile_multi_mode = enabled
        self.profile_table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
            if enabled
            else QTableWidget.SelectionMode.SingleSelection
        )
        if enabled:
            self.profile_multi_bar.setVisible(True)
        else:
            selection = sorted({index.row() for index in self.profile_table.selectedIndexes()})
            if len(selection) > 1:
                self.profile_table.selectRow(selection[0])
            self.profile_multi_bar.setVisible(False)
        self._update_profile_buttons()

    def _toggle_profile_select_all(self) -> None:
        if not self.profile_multi_mode:
            return
        rows = self.profile_table.rowCount()
        if rows and len(self._selected_profile_records()) == rows:
            self.profile_table.clearSelection()
        else:
            self.profile_table.selectAll()
        self._update_profile_buttons()

    def _show_profile_context_menu(self, position) -> None:
        index = self.profile_table.indexAt(position)
        if not index.isValid() or index.row() >= len(self._row_records):
            return
        if self.profile_multi_mode:
            self.profile_table.selectRow(index.row())
        else:
            self.profile_table.selectRow(index.row())
        self._update_profile_buttons()
        record = self._row_records[index.row()]

        menu = QMenu(self)
        if self.profile_multi_mode:
            menu.addAction(
                "删除所选配置",
                lambda: self._delete_profile_records(self._selected_profile_records()),
            )
        else:
            menu.addAction("编辑配置", lambda: self._show_profile_editor(record))
            menu.addAction("删除配置", lambda: self._delete_profile_records([record]))
        menu.addSeparator()
        menu.addAction(
            "退出多选" if self.profile_multi_mode else "多选",
            lambda: self._set_profile_multi_mode(not self.profile_multi_mode),
        )
        menu.exec(self.profile_table.viewport().mapToGlobal(position))

    def _profile_double_click(self) -> None:
        if self.profile_multi_mode:
            return
        self._switch_selected_profile()

    def _switch_selected_profile(self) -> None:
        records = self._selected_profile_records()
        if len(records) != 1 or self.profile_multi_mode or self.profile_switch_in_progress:
            return
        selected = records[0]
        config_dir = self.current_path()
        selected_key = core.normalized_path_key(selected.path)
        configured_active = core.active_profile_path(config_dir)
        pending_active = core.pending_active_profile_path(config_dir)
        resolved_active = core.resolve_active_profile(config_dir)
        selected_is_active = any(
            profile is not None and core.normalized_path_key(profile.path) == selected_key
            for profile in (resolved_active,)
        ) or any(
            path is not None and core.normalized_path_key(path) == selected_key
            for path in (configured_active, pending_active)
        )
        selected_pending = core.profile_has_pending_apply(config_dir, selected.path)
        try:
            running = (
                core.codex_restart_target(
                    core.list_windows_processes({"ChatGPT.exe", "codex.exe", "codex-code-mode-host.exe"})
                )
                is not None
            )
        except OSError as exc:
            self.show_error(f"无法检查 Codex 运行状态：\n{exc}")
            return
        if selected_is_active and running and not selected_pending:
            self.notify(f"Codex 已在使用配置：{selected.name}，并且正在运行。")
            return
        if running and not self.ask_yes_no("应用配置需要正常退出并重新启动 Codex，是否继续？"):
            return
        self.profile_switch_in_progress = True
        self.notify(
            f"正在保存当前配置并应用：{selected.name}..."
            if running
            else f"正在应用配置并启动 Codex：{selected.name}..."
        )

        def worker() -> None:
            try:
                result = core.switch_saved_profile(
                    config_dir, selected.path, allow_running_restart=running
                )
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                self.post(lambda: self._finish_profile_switch(selected, error))
                return
            self.post(lambda: self._finish_profile_switch(selected, None, result.action))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_profile_switch(
        self,
        selected: core.BackupRecord,
        error: str | None,
        action: str = "restart",
    ) -> None:
        self.profile_switch_in_progress = False
        if error:
            self.reload_current()
            self.refresh_profiles()
            self.show_error(f"切换配置失败：\n{error}")
            return
        self.reload_current()
        self.refresh_profiles(selected.path)
        self.notify(
            f"已切换到配置：{selected.name}，Codex 已启动。"
            if action == "start"
            else f"已切换到配置：{selected.name}，Codex 已重新启动。"
        )

    def _delete_profile_records(self, records: list[core.BackupRecord]) -> None:
        if not records:
            return
        if len(records) == 1:
            message = f"确定永久删除“{records[0].name}”吗？\n\n删除后无法恢复。"
        else:
            message = f"确定永久删除所选的 {len(records)} 个配置吗？\n\n删除后无法恢复。"
        if not self.ask_yes_no(message):
            return
        try:
            core.delete_backups(self.current_path(), [record.path for record in records])
        except OSError as exc:
            self.show_error(f"删除配置失败：\n{exc}")
            return
        self.reload_current()
        self.refresh_profiles()
        self.notify(f"已删除 {len(records)} 个配置。")

    def profile_result_message(self, result: core.BackupResult) -> str:
        if result.record is None:
            return "配置已保存。"
        action = "已新增配置" if result.status == "created" else "已使用已有配置"
        return f"{action}：{result.record.name}"

    # -- configuration -----------------------------------------------------

    def _set_path(self, path: Path) -> None:
        self._path = Path(path)
        self.path_edit.setText(str(path))

    def current_path(self) -> Path:
        return core.canonical_config_path(self._path)

    def _load_initial_path(self) -> None:
        settings = core.load_settings()
        possible = []
        saved = settings.get("config_dir")
        if saved:
            possible.append(Path(saved))
        possible.extend(core.candidate_config_dirs())
        for path in possible:
            if core.is_codex_config_dir(path) or core.is_official_login_mode(path):
                self._set_path(path)
                self.load_path(path)
                return
        default_path = Path.home() / ".codex"
        self._set_path(default_path)
        self.load_path(default_path)

    def choose_path(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择 Codex 配置目录",
            str(self.current_path().parent if self.current_path().parent.exists() else Path.home()),
        )
        if selected:
            self._set_path(Path(selected))
            self.load_path(Path(selected))

    def scan_paths(self) -> None:
        self.notify("正在扫描常见位置...")

        def worker() -> None:
            found = core.scan_common_locations()
            self.post(lambda: self._finish_scan(found))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_scan(self, found: list[Path]) -> None:
        if not found:
            self.notify("没有扫描到配置目录，可以点击“浏览...”手动选择。")
            return
        if len(found) == 1:
            self._set_path(found[0])
            self.load_path(found[0])
            return
        selected = ScanPickerDialog(self, found).run()
        if selected is not None:
            self._set_path(selected)
            self.load_path(selected)

    def load_path(self, path: Path) -> None:
        path = core.canonical_config_path(path)
        self._set_path(path)
        template_created = False
        template_pending = False
        first_use = not (path / "auth.json").exists() and not (path / "config.toml").exists()
        state, issues = core.classify_config_for_editing(path)
        official_login_mode = core.is_official_login_mode(path)

        if state == "editable" and official_login_mode:
            core.set_official_login_mode(path, False)
            official_login_mode = False

        if state == "needs_template" and not official_login_mode:
            if first_use:
                try:
                    core.create_custom_template_config(
                        path,
                        None,
                        core.TEMPLATE_PROVIDER_NAME,
                        core.TEMPLATE_BASE_URL,
                        core.TEMPLATE_MODEL,
                    )
                    template_created = True
                    core.set_official_login_mode(path, False)
                except OSError as exc:
                    self.show_error(f"自动创建模板失败：\n{exc}")
            else:
                template_pending = True
        elif state == "conflict" and not official_login_mode:
            self.show_error(
                "检测到复杂或冲突配置，软件不会自动覆盖。\n\n"
                + "\n".join(f"- {item}" for item in issues)
            )

        config = core.read_codex_config(path)
        self.api_key_var = config.api_key
        self.provider_var = config.provider or core.DEFAULT_PROVIDER
        self.base_url_var = config.base_url or core.DEFAULT_BASE_URL
        self.model_var = config.model or core.TEMPLATE_MODEL
        self.model_display_name_var = config.model_display_name
        self.key_entry.setText(config.api_key)
        self.provider_field.setText(self.provider_var)
        self.base_url_field.setText(self.base_url_var)
        self.model_field.setText(self.model_var)

        pending_profile = None if official_login_mode else core.pending_active_profile_path(path)
        matching_profile = (
            core.backup_record_from_path(pending_profile)
            if pending_profile is not None
            else (None if official_login_mode else core.find_matching_backup(path))
        )
        if official_login_mode:
            self.current_name_label.setText("正在使用：官方登录")
        elif matching_profile is not None:
            core.set_active_profile_path(matching_profile.path)
            self.current_name_label.setText(f"正在使用：{matching_profile.name} 配置")
        else:
            self.current_name_label.setText("未保存配置")
        core.save_settings(path)
        self._refresh_official_page()
        if hasattr(self, "profile_table") and self.active_page == "profiles":
            self.refresh_profiles()
        if template_created:
            self.notify(f"检测到首次使用，已创建可编辑配置：{path}")
            return
        if template_pending:
            self.notify("当前配置尚不可直接编辑；填写 API 配置后点击“保存配置”新增命名配置。")
            return
        if official_login_mode:
            if config.config_exists:
                self.notify("已保留 Codex 官方登录配置；可直接打开 Codex 登录 GPT 账号。")
            else:
                self.notify("已进入官方登录模式；请关闭本工具并启动 Codex，按提示登录 GPT 账号。")
            return
        markers = []
        markers.append("auth.json 已找到" if config.auth_exists else "auth.json 不存在")
        markers.append("config.toml 已找到" if config.config_exists else "config.toml 不存在")
        self.notify(f"已读取：{path}（{'，'.join(markers)}）")

    def reload_current(self) -> None:
        self.load_path(self.current_path())

    def toggle_key_visibility(self) -> None:
        self._show_key = not self._show_key
        self.key_entry.setEchoMode(
            QLineEdit.EchoMode.Normal if self._show_key else QLineEdit.EchoMode.Password
        )
        self._eye_action.setIcon(_icon_from(self.eye_off_icon if self._show_key else self.eye_icon))

    def validate_form(self) -> bool:
        path = self.current_path()
        if not str(path).strip():
            self.show_error("请先选择 Codex 配置目录。")
            return False
        base_url = self.base_url_var.strip()
        provider = self.provider_var.strip()
        model = self.model_var.strip()
        if not provider:
            self.show_error("Provider 显示名称不能为空。")
            return False
        if not base_url:
            self.show_error("Base URL 不能为空。")
            return False
        if not model:
            self.show_error("Model 不能为空。")
            return False
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            self.show_error("Base URL 需要以 http:// 或 https:// 开头。")
            return False
        return True

    def save_current(self) -> None:
        if not self.validate_form():
            return
        path = self.current_path()
        state, issues = core.classify_config_for_editing(path)
        if state == "conflict":
            self.show_error(
                "保存失败：检测到复杂或冲突配置，软件不会自动覆盖。\n\n"
                + "\n".join(f"- {item}" for item in issues)
            )
            return

        api_key = self.api_key_var
        active_provider = self.provider_var.strip()
        base_url = self.base_url_var
        model = self.model_var
        signature = core.build_requested_signature(path, api_key, active_provider, base_url, model, state)
        existing = core.find_matching_backup(path, signature)
        config_name = None
        if existing is None:
            config_name = self.ask_config_name(
                path, core.suggested_config_name(active_provider), f"新增配置：{active_provider}"
            )
            if config_name is None:
                self.notify("已取消新增配置，当前配置未修改。")
                return
        try:
            result = core.save_config_profile(
                path,
                api_key,
                active_provider,
                base_url,
                model,
                state,
                config_name,
                model_display_name="",
            )
        except (OSError, core.json.JSONDecodeError, core.BackupNameError) as exc:
            self.show_error(f"保存失败：\n{exc}")
            return
        core.set_official_login_mode(path, False)
        if result.record is not None:
            core.set_active_profile_path(result.record.path)
        result_message = self.profile_result_message(result)
        self.reload_current()
        self.notify(f"保存成功；{result_message}；当前已使用配置：{active_provider}")
        self.show_info(
            f"配置保存成功。\n\n{result_message}\n"
            f"当前已使用配置：{active_provider}\n"
            "重新打开 Codex 后通常会读取新配置。"
        )

    def restore_defaults(self) -> None:
        message = "是否进入官方登录模式？\n\n不会丢失聊天记录或已保存的 API 配置。请关闭本工具并启动 Codex，按提示登录。"
        if not self.ask_yes_no(message):
            return
        try:
            core.restore_default_config(self.current_path())
        except OSError as exc:
            self.show_error(f"恢复失败：\n{exc}")
            return
        core.set_official_login_mode(self.current_path(), True)
        core.set_pending_active_profile_path(None)
        self.api_key_var = ""
        self.provider_var = core.DEFAULT_PROVIDER
        self.base_url_var = core.DEFAULT_BASE_URL
        self.model_var = core.TEMPLATE_MODEL
        self.key_entry.setText("")
        self.provider_field.setText(self.provider_var)
        self.base_url_field.setText(self.base_url_var)
        self.model_field.setText(self.model_var)
        self.current_name_label.setText("正在使用：官方登录")
        self._refresh_official_page()
        self.refresh_profiles()
        self.notify("已进入官方登录模式，现有会话和配置均已保留。")
        self.show_info(
            "已进入官方登录模式。\n\n聊天记录和已保存的 API 配置均已保留。请关闭本工具并启动 Codex，按提示登录。"
        )

    def _refresh_official_page(self) -> None:
        official = core.is_official_login_mode(self.current_path())
        if official:
            self.official_status_label.setText("当前正在使用官方登录模式")
            self.official_action_button.setText("当前已是官方登录模式")
            self.official_action_button.setEnabled(False)
        else:
            self.official_status_label.setText("当前正在使用自定义 API 配置")
            self.official_action_button.setText("进入官方登录模式")
            self.official_action_button.setEnabled(True)

    def show_backup_settings(self) -> None:
        self.show_page("profiles")

    def open_backup_dir(self) -> None:
        backup_dir = self.current_path() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(backup_dir))


def create_application(argv: list[str] | None = None) -> QApplication:
    """Build (or reuse) the styled :class:`QApplication`.

    Factored out of :func:`main` because every harness that drives the real
    window has to configure it *identically*.  A script that constructs
    ``CodexConfigWindow`` directly and skips these lines gets an unstyled Qt
    window - default light palette, no black title bar, only the parts that
    paint themselves by hand - and then measures the wrong thing entirely.
    That is not hypothetical: it silently invalidated the first run of
    ``prototypes/verify_qt_app.py``'s visual checks.
    """
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(core.APP_NAME)
    app.setApplicationDisplayName(core.APP_NAME)
    app.setFont(QFont(FONT_FAMILY, 9))
    app.setStyleSheet(APP_QSS)
    return app


def main() -> None:
    mutex_handle = core.acquire_single_instance()
    if mutex_handle is None:
        core.show_already_running_message()
        return
    try:
        app = create_application()
        window = CodexConfigWindow()
        window.show()
        sys.exit(app.exec())
    finally:
        core.release_single_instance(mutex_handle)


if __name__ == "__main__":
    main()
