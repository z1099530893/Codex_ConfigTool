"""Count the native Windows windows behind an identical UI tree, in Tk and in Qt.

The question this answers
------------------------
``Image-Management`` is a PySide6/Qt program.  Its main window is frameless
(``Qt.WindowType.FramelessWindowHint``) - the same problem class as Tk's
``overrideredirect(True)`` - and it is translucent on top of that.  Yet it has
no recorded flicker problem anywhere in its own issue list.  The obvious
reading is "Qt solved the flicker; copy whatever Qt does".

That reading is wrong, and this script is how you check it instead of believing
it.  Qt and Tk differ in something much more basic than a window flag:

* a Tk widget **is** a native window.  ``tk.Label``, ``tk.Frame``,
  ``tk.Button`` - each one is a real ``TkChild`` HWND.  A modest Tk UI is a
  hundred windows.
* a Qt widget **is not** a native window.  ``QWidget`` renders itself into the
  top-level's backing store.  A top-level ``QWidget`` is one HWND, and the
  entire UI inside it is pixels in that one surface.

If that is true, then Qt does not "handle" the restore flicker at all - it is
structurally incapable of having it, because there is only ever one surface to
present.  And the thing worth borrowing is therefore not a flag or a snippet:
it is the single-surface architecture itself.

So: build the *same* logical UI in both frameworks - same nesting, same widget
count - and count the native windows underneath each.  The framework is the
only variable.

Modes
-----
``--tk``    build it with ``tkinter`` (``overrideredirect(True)``)
``--qt``    build it with ``PySide6`` (``FramelessWindowHint`` +
            ``WA_TranslucentBackground``, mirroring Image-Management)

Each mode prints one JSON report to stdout and a human table to stderr.  Run
them separately: Tk and Qt each want to own the process's message loop.

Usage
-----
    python proto_surface_count.py --tk
    python proto_surface_count.py --qt
    python proto_surface_count.py --both        # spawns the two above

Requires ``winapi.py`` next to this file.  ``--qt`` needs PySide6.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import winapi as W  # noqa: E402

_user32 = ctypes.windll.user32

# The same shape the real app has: a title bar with a row of controls, a dark
# sidebar with a stack of nav buttons and labels, and a light content area with
# a grid of widgets.  The counts are chosen to land near the Codex app's 56
# visible widgets / 119 total windows.
TITLE_CONTROLS = 8
SIDEBAR_CONTROLS = 14
CONTENT_CONTROLS = 24

WIDTH, HEIGHT = 820, 500
SIDEBAR_WIDTH = 142
TITLE_HEIGHT = 38

DARK = "#1e1f22"
LIGHT = "#f3f4f7"


# --------------------------------------------------------------------------- Tk
def build_tk(serve: bool = False) -> dict:
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{WIDTH}x{HEIGHT}+120+120")
    root.configure(bg=LIGHT)

    # A full-client wrapper, exactly as Tk itself nests widgets under a
    # ``TkChild`` spanning the client area.
    wrapper = tk.Frame(root, bg=LIGHT)
    wrapper.place(x=0, y=0, width=WIDTH, height=HEIGHT)

    title = tk.Frame(wrapper, bg=LIGHT, height=TITLE_HEIGHT)
    title.place(x=0, y=0, width=WIDTH, height=TITLE_HEIGHT)
    for index in range(TITLE_CONTROLS):
        tk.Label(title, text=f"t{index}", bg=LIGHT).place(
            x=8 + index * 34, y=8, width=30, height=22
        )

    body = tk.Frame(wrapper, bg=LIGHT)
    body.place(x=0, y=TITLE_HEIGHT, width=WIDTH, height=HEIGHT - TITLE_HEIGHT)

    sidebar = tk.Frame(body, bg=DARK, width=SIDEBAR_WIDTH)
    sidebar.place(x=0, y=0, width=SIDEBAR_WIDTH, height=HEIGHT - TITLE_HEIGHT)
    for index in range(SIDEBAR_CONTROLS):
        tk.Label(sidebar, text=f"s{index}", bg=DARK, fg="#ffffff").place(
            x=8, y=8 + index * 30, width=SIDEBAR_WIDTH - 16, height=26
        )

    content = tk.Frame(body, bg=LIGHT)
    content.place(
        x=SIDEBAR_WIDTH,
        y=0,
        width=WIDTH - SIDEBAR_WIDTH,
        height=HEIGHT - TITLE_HEIGHT,
    )
    for index in range(CONTENT_CONTROLS):
        column = index % 6
        row = index // 6
        tk.Label(content, text=f"c{index}", bg=LIGHT).place(
            x=10 + column * 110, y=10 + row * 60, width=100, height=50
        )

    root.update_idletasks()
    root.update()
    hwnd = int(root.winfo_id())
    # ``winfo_id`` returns the client ``TkChild``, not the real top-level
    # ``TkTopLevel`` window.  A minimize/restore has to be aimed at the
    # top-level, so hand that one out in serve mode.
    top = W.root_hwnd(hwnd)
    if serve:
        sys.stdout.write(f"SERVE_HWND={top:#x}\n")
        sys.stdout.flush()
        root.mainloop()
    return collect(hwnd, "tk", root=root)


# ------------------------------------------------------------------ Tk canvas
def build_tk_canvas(serve: bool = False, alpha: float | None = None) -> dict:
    """The same UI, drawn into **one** ``tk.Canvas``.

    This is the cheap version of the Qt architecture.  A ``tk.Canvas`` is a
    single native window that owns all of its pixels, so the whole view layer
    collapses to one HWND - the same property that makes the Qt window immune
    to the restore flicker - without changing toolkit, packaging, or any of the
    application's non-UI code.

    Same size, same colours, same content as the widget version, so the two are
    directly comparable: the only difference is how many native windows the
    view layer is made of.

    ``alpha`` sets Tk's ``-alpha`` attribute, which is how Tk itself applies
    ``WS_EX_LAYERED`` on Windows.  Worth testing because the Qt window is
    layered *and* clean, and it is not obvious which of those two properties
    does the work.
    """
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{WIDTH}x{HEIGHT}+120+120")
    root.configure(bg=LIGHT)

    canvas = tk.Canvas(
        root,
        width=WIDTH,
        height=HEIGHT,
        highlightthickness=0,
        bd=0,
        bg=LIGHT,
    )
    canvas.place(x=0, y=0, width=WIDTH, height=HEIGHT)

    # Title bar
    canvas.create_rectangle(0, 0, WIDTH, TITLE_HEIGHT, fill=LIGHT, outline="")
    for index in range(TITLE_CONTROLS):
        canvas.create_text(
            8 + index * 34 + 15,
            TITLE_HEIGHT // 2,
            text=f"t{index}",
            fill="#111111",
        )

    body_height = HEIGHT - TITLE_HEIGHT

    # Sidebar - keep the bottom 40 px clear so the probe strip lands on plain
    # background rather than on a drawn item.
    canvas.create_rectangle(
        0, TITLE_HEIGHT, SIDEBAR_WIDTH, HEIGHT, fill=DARK, outline=""
    )
    for index in range(SIDEBAR_CONTROLS):
        canvas.create_text(
            8,
            TITLE_HEIGHT + 8 + index * 30 + 13,
            text=f"s{index}",
            fill="#ffffff",
            anchor="w",
        )

    # Content
    for index in range(CONTENT_CONTROLS):
        column = index % 6
        row = index // 6
        left = SIDEBAR_WIDTH + 10 + column * 110
        # Not ``top`` - that name holds the window handle above.
        card_top = TITLE_HEIGHT + 10 + row * 60
        canvas.create_rectangle(
            left, card_top, left + 100, card_top + 50, fill="#ffffff", outline=""
        )
        canvas.create_text(
            left + 8, card_top + 25, text=f"c{index}", fill="#111111", anchor="w"
        )

    _ = body_height
    if alpha is not None:
        # Tk's own route to ``WS_EX_LAYERED``.  Raw ``SetWindowLongPtr`` on a
        # window Tk has already mapped breaks its painting outright, and
        # applying it before the first map is not reachable through
        # ``withdraw()`` (the window then fails to map at all, 1x1).  Going
        # through Tk means Tk knows about the redirection and cooperates.
        root.attributes("-alpha", alpha)

    name = "tk-canvas-alpha" if alpha is not None else "tk-canvas"
    root.update_idletasks()
    root.update()
    hwnd = int(root.winfo_id())
    top = W.root_hwnd(hwnd)
    if serve:
        sys.stdout.write(f"SERVE_HWND={top:#x}\n")
        sys.stdout.flush()
        root.mainloop()
    return collect(hwnd, name, root=root)


# --------------------------------------------------------------------------- Qt
def build_qt(serve: bool = False) -> dict:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )

    app = QApplication.instance() or QApplication(sys.argv)

    class MainWindow(QWidget):
        """Structurally the Image-Management main window, at Codex app size.

        Same constructor flags (``FramelessWindowHint | Window``), same
        ``WA_TranslucentBackground``, same nested ``QFrame`` layout, same
        custom title bar / sidebar / content split.
        """

        def __init__(self) -> None:
            super().__init__(
                None,
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window,
            )
            self.setWindowTitle("proto-surface-count")
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.resize(WIDTH, HEIGHT)

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            surface = QFrame()
            surface.setObjectName("surface")
            surface.setStyleSheet(f"QFrame#surface{{background:{LIGHT};}}")
            root.addWidget(surface)
            surface_layout = QVBoxLayout(surface)
            surface_layout.setContentsMargins(0, 0, 0, 0)
            surface_layout.setSpacing(0)

            title = QFrame()
            title.setFixedHeight(TITLE_HEIGHT)
            title.setStyleSheet(f"background:{LIGHT};")
            title_layout = QHBoxLayout(title)
            title_layout.setContentsMargins(8, 8, 8, 8)
            title_layout.setSpacing(4)
            for index in range(TITLE_CONTROLS):
                label = QLabel(f"t{index}")
                label.setFixedSize(30, 22)
                title_layout.addWidget(label)
            title_layout.addStretch(1)
            surface_layout.addWidget(title)

            body = QFrame()
            body_layout = QHBoxLayout(body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(0)

            sidebar = QFrame()
            sidebar.setFixedWidth(SIDEBAR_WIDTH)
            sidebar.setStyleSheet(f"background:{DARK};color:#ffffff;")
            sidebar_layout = QVBoxLayout(sidebar)
            sidebar_layout.setContentsMargins(8, 8, 8, 8)
            sidebar_layout.setSpacing(4)
            for index in range(SIDEBAR_CONTROLS):
                label = QLabel(f"s{index}")
                label.setFixedHeight(26)
                sidebar_layout.addWidget(label)
            sidebar_layout.addStretch(1)
            body_layout.addWidget(sidebar)

            content = QFrame()
            content.setStyleSheet(f"background:{LIGHT};")
            content_layout = QGridLayout(content)
            content_layout.setContentsMargins(10, 10, 10, 10)
            content_layout.setSpacing(10)
            for index in range(CONTENT_CONTROLS):
                label = QLabel(f"c{index}")
                label.setFixedSize(100, 50)
                content_layout.addWidget(label, index // 6, index % 6)
            body_layout.addWidget(content, 1)

            surface_layout.addWidget(body, 1)

        def report(self) -> dict:
            return collect(int(self.winId()), "qt")

    window = MainWindow()
    window.show()

    if serve:
        def announce() -> None:
            sys.stdout.write(f"SERVE_HWND={int(window.winId()):#x}\n")
            sys.stdout.flush()

        # Wait for the platform window to exist and be laid out before telling
        # the driver where to point.
        QTimer.singleShot(1200, announce)
        app.exec()
        return {}

    result: dict = {}

    def finish() -> None:
        result.update(window.report())
        app.quit()

    # Let Qt actually create the platform window and lay out before counting.
    QTimer.singleShot(1200, finish)
    app.exec()
    return result


# ------------------------------------------------------------------------ census
def collect(hwnd: int, framework: str, root=None) -> dict:
    """Enumerate every native window under ``hwnd`` and describe the shape."""
    descendants = W.child_windows(hwnd)
    direct = W.direct_children(hwnd)

    entries = []
    for index, child in enumerate(descendants):
        left, top, width, height = W.window_rect(child)
        parent_left, parent_top, _, _ = W.window_rect(hwnd)
        entries.append(
            {
                "index": index,
                "hwnd": f"{child:#x}",
                "class": W.class_name(child),
                "rel": [left - parent_left, top - parent_top, width, height],
                "visible": W.is_visible(child),
            }
        )

    by_class: dict[str, int] = {}
    for entry in entries:
        by_class[entry["class"]] = by_class.get(entry["class"], 0) + 1

    top_style = W.get_style(hwnd)
    top_ex_style = W.get_ex_style(hwnd)

    report = {
        "framework": framework,
        "toplevel": {
            "hwnd": f"{hwnd:#x}",
            "class": W.class_name(hwnd),
            "style": f"0x{top_style:08X}",
            "exstyle": f"0x{top_ex_style:08X}",
            "size": list(W.window_rect(hwnd)[2:]),
            "taskbar": W.would_appear_in_taskbar(hwnd),
        },
        "native_descendants": len(descendants),
        "native_direct_children": len(direct),
        "visible_native_descendants": sum(1 for e in entries if e["visible"]),
        "by_class": dict(sorted(by_class.items(), key=lambda kv: -kv[1])),
        "descendants": entries,
    }

    if root is not None:
        # Tk knows how many widgets it created; the gap between that number and
        # the native window count is the whole point of the comparison.
        report["toolkit_widgets"] = len(root.winfo_children()) + _tk_depth(root)

    _print_table(report)
    return report


def _tk_depth(widget) -> int:
    total = 0
    for child in widget.winfo_children():
        total += 1 + _tk_depth(child)
    return total


def _print_table(report: dict) -> None:
    top = report["toplevel"]
    print(f"--- {report['framework']} ---", file=sys.stderr)
    print(
        f"toplevel {top['class']} style={top['style']} exstyle={top['exstyle']} "
        f"{top['size'][0]}x{top['size'][1]}",
        file=sys.stderr,
    )
    print(
        f"native descendants: {report['native_descendants']} "
        f"(direct {report['native_direct_children']}, "
        f"visible {report['visible_native_descendants']})",
        file=sys.stderr,
    )
    print(f"by class: {report['by_class']}", file=sys.stderr)
    if "toolkit_widgets" in report:
        print(f"toolkit widgets created: {report['toolkit_widgets']}", file=sys.stderr)


# --------------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tk", action="store_true")
    parser.add_argument(
        "--tk-canvas",
        action="store_true",
        help="the same UI drawn into one tk.Canvas - the cheap route to one surface",
    )
    parser.add_argument(
        "--tk-canvas-composited",
        action="store_true",
        help="the canvas UI plus Tk's -alpha (which applies WS_EX_LAYERED)",
    )
    parser.add_argument("--qt", action="store_true")
    parser.add_argument("--both", action="store_true")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="show the window, print its top-level hwnd, then idle for a driver",
    )
    parser.add_argument(
        "--out",
        default=os.path.join(HERE, "out", "surface-count.json"),
    )
    args = parser.parse_args()

    if not (args.tk or args.tk_canvas or args.tk_canvas_composited
            or args.qt or args.both):
        args.both = True

    reports = []
    if args.tk:
        reports.append(build_tk(serve=args.serve))
    if args.tk_canvas:
        reports.append(build_tk_canvas(serve=args.serve))
    if args.tk_canvas_composited:
        reports.append(build_tk_canvas(serve=args.serve, alpha=0.99))
    if args.qt:
        reports.append(build_qt(serve=args.serve))
    if args.both:
        # Each framework wants its own process: run ourselves once per variant.
        for flag in ("--tk", "--tk-canvas", "--qt"):
            completed = subprocess.run(
                [sys.executable, os.path.abspath(__file__), flag],
                capture_output=True,
                text=True,
                timeout=120,
            )
            sys.stderr.write(completed.stderr)
            if completed.returncode != 0:
                print(
                    f"{flag} failed rc={completed.returncode}",
                    file=sys.stderr,
                )
                continue
            reports.append(json.loads(completed.stdout))

    if not reports:
        return 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(reports, handle, indent=2)

    if len(reports) > 1:
        print("", file=sys.stderr)
        print("=== verdict ===", file=sys.stderr)
        for report in reports:
            print(
                f"{report['framework']:>9}: {report['native_descendants']:>3} "
                f"native windows under the client area",
                file=sys.stderr,
            )

    print(json.dumps(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
