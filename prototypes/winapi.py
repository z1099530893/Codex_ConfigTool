"""Thin Win32 helpers shared by the window prototype and the validation harness.

Everything here is deliberately small and side-effect free so the same code can
be imported by the prototype, by the test suite and by the checker script.
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

GWL_STYLE = -16
GWL_EXSTYLE = -20
GW_OWNER = 4
GA_ROOT = 2
GA_PARENT = 1

WS_CAPTION = 0x00C00000
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000

WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_WINDOWEDGE = 0x00000100
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_DLGMODALFRAME = 0x00000001
WS_EX_STATICEDGE = 0x00020000

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_RESTORE = 9

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

WM_SYSCOMMAND = 0x0112
SC_RESTORE = 0xF120
SC_MINIMIZE = 0xF020

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _get_long = user32.GetWindowLongPtrW
    _set_long = user32.SetWindowLongPtrW
else:  # pragma: no cover - 32-bit fallback
    _get_long = user32.GetWindowLongW
    _set_long = user32.SetWindowLongW

_get_long.argtypes = (wintypes.HWND, ctypes.c_int)
_get_long.restype = ctypes.c_void_p
_set_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
_set_long.restype = ctypes.c_void_p

user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.GetParent.argtypes = (wintypes.HWND,)
user32.GetParent.restype = wintypes.HWND
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetWindow.restype = wintypes.HWND
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetClientRect.restype = wintypes.BOOL
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = (
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.SetWindowPos.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = (wintypes.POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.SetFocus.argtypes = (wintypes.HWND,)
user32.SetFocus.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.EnumDisplayMonitors.argtypes = (
    wintypes.HDC,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.LPARAM,
)
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
user32.GetMonitorInfoW.restype = wintypes.BOOL

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2


def as_hwnd(value) -> int:
    """Coerce anything HWND-ish (int, c_void_p, None) into a plain int."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def root_hwnd(hwnd) -> int:
    """Return the top-level (root) HWND for a widget handle.

    ``winfo_id()`` on Windows returns Tk's inner window, whose root ancestor is
    the decorated wrapper window that Windows actually manages.
    """
    hwnd = as_hwnd(hwnd)
    if not hwnd:
        return 0
    root = as_hwnd(user32.GetAncestor(wintypes.HWND(hwnd), GA_ROOT))
    return root or hwnd


def class_name(hwnd) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    if not user32.GetClassNameW(wintypes.HWND(as_hwnd(hwnd)), buffer, 256):
        return ""
    return buffer.value


def get_style(hwnd) -> int:
    return int(_get_long(wintypes.HWND(as_hwnd(hwnd)), GWL_STYLE) or 0)


def get_ex_style(hwnd) -> int:
    return int(_get_long(wintypes.HWND(as_hwnd(hwnd)), GWL_EXSTYLE) or 0)


def set_ex_style(hwnd, value: int) -> None:
    _set_long(wintypes.HWND(as_hwnd(hwnd)), GWL_EXSTYLE, ctypes.c_void_p(value))


def window_rect(hwnd) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32.GetWindowRect(wintypes.HWND(as_hwnd(hwnd)), ctypes.byref(rect))
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def client_rect(hwnd) -> tuple[int, int]:
    rect = wintypes.RECT()
    user32.GetClientRect(wintypes.HWND(as_hwnd(hwnd)), ctypes.byref(rect))
    return (rect.right - rect.left, rect.bottom - rect.top)


def frame_thickness(hwnd) -> tuple[int, int]:
    """Return (horizontal, vertical) non-client frame size in pixels.

    A window showing a native title bar reports a vertical frame of roughly
    30+ pixels; a borderless window reports (0, 0).
    """
    _, _, window_width, window_height = window_rect(hwnd)
    client_width, client_height = client_rect(hwnd)
    return (window_width - client_width, window_height - client_height)


def is_iconic(hwnd) -> bool:
    return bool(user32.IsIconic(wintypes.HWND(as_hwnd(hwnd))))


def is_visible(hwnd) -> bool:
    return bool(user32.IsWindowVisible(wintypes.HWND(as_hwnd(hwnd))))


def has_owner(hwnd) -> bool:
    return bool(as_hwnd(user32.GetWindow(wintypes.HWND(as_hwnd(hwnd)), GW_OWNER)))


def would_appear_in_taskbar(hwnd) -> bool:
    """Apply the documented shell rule for taskbar button eligibility."""
    hwnd = as_hwnd(hwnd)
    if not hwnd or not user32.IsWindow(wintypes.HWND(hwnd)):
        return False
    ex_style = get_ex_style(hwnd)
    if ex_style & WS_EX_TOOLWINDOW:
        return False
    if has_owner(hwnd) and not (ex_style & WS_EX_APPWINDOW):
        return False
    return True


def apply_taskbar_appwindow(hwnd) -> None:
    """Make an unowned/undecorated window eligible for a taskbar button."""
    hwnd = as_hwnd(hwnd)
    ex_style = get_ex_style(hwnd)
    ex_style = (ex_style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
    set_ex_style(hwnd, ex_style)
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


def strip_decorations(hwnd) -> int:
    """Remove caption/border style bits, keeping the window OS-managed.

    Returns the previous style.  Unlike ``overrideredirect`` this keeps the
    window a normal overlapped top-level window, so the taskbar button, native
    minimize animation and native restore all keep working.
    """
    hwnd = as_hwnd(hwnd)
    style = get_style(hwnd)
    stripped = style & ~(
        WS_CAPTION
        | WS_BORDER
        | WS_DLGFRAME
        | WS_THICKFRAME
        | WS_SYSMENU
        | WS_MINIMIZEBOX
        | WS_MAXIMIZEBOX
    )
    stripped |= WS_POPUP & style  # keep popup-ness only if it was already popup
    _set_long(wintypes.HWND(hwnd), GWL_STYLE, ctypes.c_void_p(stripped))
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )
    return style


def minimize_window(hwnd) -> bool:
    return bool(user32.ShowWindow(wintypes.HWND(as_hwnd(hwnd)), SW_MINIMIZE))


def restore_window(hwnd) -> bool:
    hwnd = as_hwnd(hwnd)
    result = bool(user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE))
    user32.SetForegroundWindow(wintypes.HWND(hwnd))
    return result


# --------------------------------------------------------------------------- #
# occlusion
# --------------------------------------------------------------------------- #
#
# Synthetic mouse input goes to whatever window is topmost under the cursor, not
# to the window the test means to click.  On a shared desktop a modal dialog from
# another application can sit exactly on top of the window under test, which
# silently turns "the button did not work" into "the click never arrived".  These
# helpers make that condition detectable and correctable instead of invisible.


def window_at(x: int, y: int) -> int:
    """The window directly under a screen point, or 0."""
    return as_hwnd(user32.WindowFromPoint(wintypes.POINT(x, y)))


def root_at(x: int, y: int) -> int:
    """The top-level window directly under a screen point, or 0."""
    hwnd = window_at(x, y)
    return root_hwnd(hwnd) if hwnd else 0


def is_clickable(hwnd, x: int, y: int) -> bool:
    """True when a click at ``(x, y)`` would land on ``hwnd``."""
    return root_at(x, y) == as_hwnd(hwnd)


def describe_occluder(hwnd, x: int, y: int) -> str:
    """Describe whatever sits under ``(x, y)`` instead of ``hwnd``."""
    top = root_at(x, y)
    if not top:
        return "nothing"
    return f"hwnd={top:#x} class={class_name(top)!r} title={window_text(top)[:40]!r}"


def raise_window(hwnd) -> bool:
    """Try to put ``hwnd`` in front, working around the foreground lock.

    ``SetForegroundWindow`` is refused unless the caller already owns the
    foreground, so the calling thread is briefly attached to the current
    foreground thread, which lifts that restriction.
    """
    hwnd = as_hwnd(hwnd)
    if not hwnd:
        return False
    foreground = as_hwnd(user32.GetForegroundWindow())
    if foreground == hwnd:
        return True
    current_thread = _kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), None)
    foreground_thread = (
        user32.GetWindowThreadProcessId(wintypes.HWND(foreground), None) if foreground else 0
    )
    attached = []
    for thread in {foreground_thread, current_thread}:
        if thread and thread != target_thread:
            if user32.AttachThreadInput(thread, target_thread, True):
                attached.append(thread)
    try:
        user32.BringWindowToTop(wintypes.HWND(hwnd))
        user32.SetForegroundWindow(wintypes.HWND(hwnd))
        user32.SetFocus(wintypes.HWND(hwnd))
    finally:
        for thread in attached:
            user32.AttachThreadInput(thread, target_thread, False)
    return as_hwnd(user32.GetForegroundWindow()) == hwnd


def foreground_hwnd() -> int:
    """The window that currently owns the foreground, or 0."""
    return as_hwnd(user32.GetForegroundWindow())


SC_SIZE = 0xF000
SC_MOVE = 0xF010
SC_MINIMIZE = 0xF020
SC_MAXIMIZE = 0xF030
SC_CLOSE = 0xF060
SC_RESTORE = 0xF120

MF_BYCOMMAND = 0x00000000
MF_GRAYED = 0x00000001
MF_DISABLED = 0x00000002

_SC_NAMES = {
    SC_SIZE: "Size",
    SC_MOVE: "Move",
    SC_MINIMIZE: "Minimize",
    SC_MAXIMIZE: "Maximize",
    SC_CLOSE: "Close",
    SC_RESTORE: "Restore",
}

user32.GetSystemMenu.argtypes = (wintypes.HWND, wintypes.BOOL)
user32.GetSystemMenu.restype = wintypes.HMENU
user32.GetMenuState.argtypes = (wintypes.HMENU, wintypes.UINT, wintypes.UINT)
user32.GetMenuState.restype = wintypes.UINT


def system_menu_report(hwnd) -> dict:
    """What the taskbar jump list would offer, read off the window's system menu.

    A window with no ``WS_SYSMENU`` has no system menu at all, which is one of
    the signals that makes the Shell treat its taskbar button as activate-only.
    """
    hwnd = as_hwnd(hwnd)
    if not hwnd:
        return {"system_menu": None, "note": "no window"}
    menu = user32.GetSystemMenu(wintypes.HWND(hwnd), False)
    if not menu:
        return {"system_menu": None, "note": "window has no system menu at all"}
    items = {}
    for command, name in _SC_NAMES.items():
        state = user32.GetMenuState(menu, command, MF_BYCOMMAND)
        if state == 0xFFFFFFFF:
            items[name] = "absent"
            continue
        flags = []
        if state & MF_GRAYED:
            flags.append("GRAYED")
        if state & MF_DISABLED:
            flags.append("DISABLED")
        items[name] = ",".join(flags) if flags else "enabled"
    return {"system_menu": hex(menu), "items": items}


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, wintypes.HDC, ctypes.c_void_p, wintypes.LPARAM
)


def monitor_rects() -> list[tuple[int, int, int, int]]:
    """Every monitor's bounds as ``(left, top, right, bottom)``.

    Monitors do not have to be aligned with each other.  On the machine this
    harness was developed on the primary is ``(0,0)-(1920,1080)`` while the
    secondary is ``(1920,69)-(3840,1149)``, so the band ``x < 1920, y >= 1080``
    belongs to no monitor at all.  Windows silently clamps the cursor out of
    such a band, which is indistinguishable from input injection failing.
    """
    rects: list[tuple[int, int, int, int]] = []

    def callback(hmonitor, _hdc, _rect, _data):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitor = info.rcMonitor
            rects.append((monitor.left, monitor.top, monitor.right, monitor.bottom))
        return 1

    user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(callback), 0)
    return rects


def on_a_monitor(x: int, y: int) -> bool:
    """True when a screen point lands on some monitor rather than in a gap."""
    return any(
        left <= x < right and top <= y < bottom
        for left, top, right, bottom in monitor_rects()
    )


def primary_monitor_size() -> tuple[int, int]:
    """Size of the primary monitor, which is always anchored at ``(0, 0)``."""
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def make_foreground(hwnd, timeout: float = 3.0) -> bool:
    """Raise ``hwnd`` and wait until Windows agrees that it is foreground.

    ``raise_window`` can report success while another process immediately
    reclaims the foreground, so this re-checks and retries briefly.  The
    foreground owner matters to tests: a taskbar button only carries its
    "active" highlight while its window owns the foreground, so capturing a
    taskbar baseline from a background window yields a strip with no
    distinguishable button in it.
    """
    hwnd = as_hwnd(hwnd)
    if not hwnd:
        return False
    deadline = time.time() + timeout
    while True:
        if foreground_hwnd() == hwnd:
            return True
        raise_window(hwnd)
        if foreground_hwnd() == hwnd:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.15)


def pin_on_top(hwnd, on: bool = True) -> None:
    """Place ``hwnd`` in the topmost band (or drop it out again).

    Needed when a modal dialog from another process keeps reclaiming the
    foreground: topmost placement is not subject to the foreground lock.
    """
    user32.SetWindowPos(
        wintypes.HWND(as_hwnd(hwnd)),
        wintypes.HWND(HWND_TOPMOST if on else HWND_NOTOPMOST),
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


def ensure_clickable(hwnd, x: int, y: int, allow_pin: bool = True) -> tuple[bool, str]:
    """Make ``hwnd`` the window a click at ``(x, y)`` would actually reach.

    Escalates only as far as necessary and reports what it had to do, so a test
    can distinguish a healthy run from one that needed help.  Returns
    ``(ok, detail)``.
    """
    hwnd = as_hwnd(hwnd)
    if is_clickable(hwnd, x, y):
        return True, "already-topmost"
    blocked_by = describe_occluder(hwnd, x, y)
    raise_window(hwnd)
    if is_clickable(hwnd, x, y):
        return True, f"raised (was behind {blocked_by})"
    if allow_pin:
        pin_on_top(hwnd, True)
        if is_clickable(hwnd, x, y):
            return True, f"pinned topmost (was behind {blocked_by})"
    return False, f"still occluded by {blocked_by}"



def make_overlapped_without_caption(hwnd) -> int:
    """Turn a ``WS_POPUP`` wrapper into a normal undecorated overlapped window.

    ``overrideredirect`` makes Tk set ``WS_POPUP`` on the toplevel wrapper.  The
    shell refuses a taskbar button for such a window.  Clearing ``WS_POPUP`` and
    all decoration bits yields a plain overlapped window with a zero-sized
    non-client area: the shell treats it like any normal app window, while Tk
    still believes the window is borderless and therefore adds no frame.
    """
    hwnd = as_hwnd(hwnd)
    style = get_style(hwnd)
    style &= ~(
        WS_POPUP
        | WS_CAPTION
        | WS_BORDER
        | WS_DLGFRAME
        | WS_THICKFRAME
        | WS_SYSMENU
        | WS_MINIMIZEBOX
        | WS_MAXIMIZEBOX
    )
    _set_long(wintypes.HWND(hwnd), GWL_STYLE, ctypes.c_void_p(style))
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )
    return style


def force_taskbar_reevaluation(hwnd) -> None:
    """Nudge the shell into re-deciding whether this window gets a taskbar button.

    Toggling ``WS_EX_TOOLWINDOW`` is the documented way to make the shell add or
    remove a taskbar button.  Crucially this does *not* hide the window, so Tk
    never sees an Unmap/Map pair and cannot disturb the geometry.
    """
    hwnd = as_hwnd(hwnd)
    set_ex_style(hwnd, get_ex_style(hwnd) | WS_EX_TOOLWINDOW)
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )
    set_ex_style(hwnd, (get_ex_style(hwnd) & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        None,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


def describe(hwnd) -> str:
    hwnd = as_hwnd(hwnd)
    style = get_style(hwnd)
    ex_style = get_ex_style(hwnd)
    _, _, width, height = window_rect(hwnd)
    client_width, client_height = client_rect(hwnd)
    return (
        f"hwnd=0x{hwnd:X} class={class_name(hwnd)!r} style=0x{style:08X} "
        f"exstyle=0x{ex_style:08X} window={width}x{height} "
        f"client={client_width}x{client_height} frame={frame_thickness(hwnd)} "
        f"iconic={is_iconic(hwnd)} visible={is_visible(hwnd)} "
        f"taskbar={would_appear_in_taskbar(hwnd)}"
    )


# ------------------------------------------------------- ITaskbarList (shell)
# The supported way to give a window a taskbar button when the shell did not
# create one itself (e.g. because the window was popup/toolwindow when first
# shown).  Unlike hide/show tricks it does not touch geometry at all.
CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_ITaskbarList = "{56FDF342-FD6D-11d0-958A-006097C9A090}"
CLSCTX_INPROC_SERVER = 0x1
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = -2147417850  # 0x80010106


def _parse_guid(text: str):
    body = text.strip("{}")
    parts = body.split("-")
    data4 = bytes.fromhex(parts[3] + parts[4])
    return GUID(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16), (ctypes.c_ubyte * 8)(*data4))


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_HRINIT = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
_ADDTAB = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND)
_RELEASE = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)

_taskbar_list_cache: dict = {"ptr": None}


def taskbar_add_tab(hwnd) -> bool:
    """Register ``hwnd`` with the shell so it gets a taskbar button."""
    hwnd = as_hwnd(hwnd)
    if not hwnd:
        return False

    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoCreateInstance.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )
    ole32.CoCreateInstance.restype = ctypes.c_long

    result = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if result not in (0, 1, RPC_E_CHANGED_MODE):
        return False

    pointer = _taskbar_list_cache.get("ptr")
    if not pointer:
        clsid = _parse_guid(CLSID_TaskbarList)
        iid = _parse_guid(IID_ITaskbarList)
        raw = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, CLSCTX_INPROC_SERVER, ctypes.byref(iid), ctypes.byref(raw)
        )
        if hr != 0 or not raw.value:
            return False
        vtable = ctypes.cast(
            ctypes.cast(raw, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )
        # 0 QueryInterface, 1 AddRef, 2 Release, 3 HrInit, 4 AddTab, 5 DeleteTab
        if _HRINIT(vtable[3])(raw) != 0:
            return False
        pointer = raw
        _taskbar_list_cache["ptr"] = raw

    vtable = ctypes.cast(
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0],
        ctypes.POINTER(ctypes.c_void_p),
    )
    return _ADDTAB(vtable[4])(pointer, wintypes.HWND(hwnd)) == 0


def taskbar_delete_tab(hwnd) -> bool:
    hwnd = as_hwnd(hwnd)
    pointer = _taskbar_list_cache.get("ptr")
    if not hwnd or not pointer:
        return False
    vtable = ctypes.cast(
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0],
        ctypes.POINTER(ctypes.c_void_p),
    )
    return _ADDTAB(vtable[5])(pointer, wintypes.HWND(hwnd)) == 0


# --------------------------------------------------------------------- taskbar
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumChildWindows.argtypes = (wintypes.HWND, _WNDENUMPROC, wintypes.LPARAM)
user32.EnumChildWindows.restype = wintypes.BOOL
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int


def window_text(hwnd) -> str:
    length = user32.GetWindowTextLengthW(wintypes.HWND(as_hwnd(hwnd)))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(wintypes.HWND(as_hwnd(hwnd)), buffer, length + 1)
    return buffer.value


def _descendants(parent) -> list[int]:
    found: list[int] = []

    def callback(hwnd, _lparam):
        found.append(as_hwnd(hwnd))
        return True

    user32.EnumChildWindows(wintypes.HWND(as_hwnd(parent)), _WNDENUMPROC(callback), 0)
    return found


def taskbar_button_labels() -> list[str]:
    """Read the labels of the real taskbar buttons from the shell's task list.

    **This returns an empty list on Windows 11, so do not use it to assert that a
    taskbar button exists.**  It walks the ``MSTaskListWClass`` button children
    and reads their window text, which is how the classic (Windows 7-10) taskbar
    was built.  Measured on this machine (Windows 11): ``Shell_TrayWnd`` is
    present, ``MSTaskListWClass`` is present, and it has **no** text-bearing
    descendant buttons - so the function reports 0 labels for a window that
    plainly does have a taskbar button.  The helper was written for the older
    shell and had never been called, which is why the claim went unchallenged.

    Use instead, depending on what is actually needed:

    * a style-based proxy - ``would_appear_in_taskbar(hwnd)``, or the
      ``WS_SYSMENU | WS_MINIMIZEBOX`` bits directly;
    * presence in the real taskbar - screen capture diffed across states, which
      is what ``accept_packaged_exe.py`` does, and which additionally requires
      the window to own the foreground for the active highlight to show.
    """
    tray = as_hwnd(user32.FindWindowW("Shell_TrayWnd", None))
    if not tray:
        return []
    labels: list[str] = []
    for child in _descendants(tray):
        if class_name(child) != "MSTaskListWClass":
            continue
        for button in _descendants(child):
            text = window_text(button)
            if text:
                labels.append(text)
    return labels


def taskbar_has_window_title(title: str) -> bool:
    """True when a taskbar button whose label contains ``title`` exists."""
    title = title.strip().lower()
    return any(title in label.strip().lower() for label in taskbar_button_labels())


DWMWA_EXTENDED_FRAME_BOUNDS = 9


def dwm_frame_bounds(hwnd) -> tuple[int, int, int, int] | None:
    """The rect DWM is actually compositing for ``hwnd``.

    During a minimize/restore transition the HWND rect is already final while DWM
    is still animating the *visual* position, so the two disagree.  Comparing them
    tells a repaint problem (equal) apart from a transition artefact (different),
    which is the difference between an app bug and a Windows animation.

    Returns ``(left, top, width, height)`` like :func:`window_rect`, or ``None``
    when DWM has no opinion (no composition, or the call failed).
    """
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:
        return None
    dwmapi.DwmGetWindowAttribute.argtypes = (
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    rect = wintypes.RECT()
    result = dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(as_hwnd(hwnd)),
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if result != 0:
        return None
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


# RedrawWindow flags (winuser.h)
RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_FRAME = 0x0400
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100
RDW_ERASENOW = 0x0200


def sync_redraw_all(hwnd) -> bool:
    """Force the window and every descendant to repaint right now.

    Windows normally spreads the repaint of a restored window across several
    passes of the message loop, which is what makes the child windows appear one
    after another.  ``RDW_ALLCHILDREN | RDW_UPDATENOW`` collapses that into a
    single synchronous pass before the call returns.
    """
    return bool(
        user32.RedrawWindow(
            wintypes.HWND(as_hwnd(hwnd)),
            None,
            None,
            RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_ERASENOW,
        )
    )


# --------------------------------------------------------------------------- #
# Background erase suppression (window-procedure subclass)
# --------------------------------------------------------------------------- #

WM_ERASEBKGND = 0x0014
GWLP_WNDPROC = -4

_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(
    _LRESULT, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t
)

# hwnd -> (python callback, previous window proc, counters).  The callback object
# must be kept alive: Windows holds a raw function pointer, and a garbage
# collected thunk would crash the process on the next message.
_subclassed: dict[int, tuple] = {}


def suppress_background_erase(hwnd) -> bool:
    """Make ``WM_ERASEBKGND`` a no-op for this window.

    The captured frame timeline shows the restored window as
    *correct -> uniform background -> correct*: the window is painted properly,
    then something erases it, then it is painted again.  Windows erases a window
    before repainting it whenever the background is invalidated, and for a
    borderless window whose content has not changed that erase is pure loss - it
    replaces correct pixels with a flat fill for the duration of the repaint.

    Returning 1 from ``WM_ERASEBKGND`` means "handled, do not erase", so the old
    pixels survive until the real paint arrives.  Note this is *not* what
    clearing ``GCLP_HBRBACKGROUND`` tests: Tk handles the erase itself rather
    than relying on the class brush, so the brush has to be intercepted in the
    window procedure to observe any effect.
    """
    hwnd = as_hwnd(hwnd)
    if not hwnd or hwnd in _subclassed:
        return hwnd in _subclassed

    get_long = user32.GetWindowLongPtrW
    get_long.argtypes = (wintypes.HWND, ctypes.c_int)
    get_long.restype = ctypes.c_ssize_t
    set_long = user32.SetWindowLongPtrW
    set_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    set_long.restype = ctypes.c_ssize_t
    call_proc = user32.CallWindowProcW
    call_proc.argtypes = (
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    )
    call_proc.restype = ctypes.c_ssize_t

    previous = get_long(wintypes.HWND(hwnd), GWLP_WNDPROC)
    if not previous:
        return False

    counters = {"erase": 0}

    def window_proc(h, message, wparam, lparam):
        if message == WM_ERASEBKGND:
            counters["erase"] += 1
            return 1
        return call_proc(previous, h, message, wparam, lparam)

    callback = _WNDPROC(window_proc)
    set_long(wintypes.HWND(hwnd), GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p).value)
    _subclassed[hwnd] = (callback, previous, counters)
    return True


def background_erase_count(hwnd) -> int:
    """How many ``WM_ERASEBKGND`` messages the subclass has swallowed."""
    entry = _subclassed.get(as_hwnd(hwnd))
    return entry[2]["erase"] if entry else 0


# --------------------------------------------------------------------------- #
# LockWindowUpdate (make a repaint atomic)
# --------------------------------------------------------------------------- #

def lock_window_update(hwnd) -> bool:
    """Freeze painting for this window and all its children.

    The frame timeline shows the restored window as *correct -> uniform
    background -> correct*, and the blank coincides with the end of the burst of
    ~114 ``<Map>`` events (first callback at ~10 ms, burst ends at ~57-62 ms,
    blank frame at ~64 ms).  So the tear is a full redraw that Tk performs after
    the map storm: the parent's background is painted first and the child windows
    follow over the next ~20 ms, and every intermediate state reaches the screen.

    Suppressing ``WM_ERASEBKGND`` does not help (measured), because the
    background is painted by Tk inside ``WM_PAINT`` rather than by an erase.
    ``LockWindowUpdate`` suppresses *all* painting for the window and its
    descendants and accumulates the invalid region instead, so the screen keeps
    the last correct frame until the lock is released and the whole tree paints
    in one pass.
    """
    lock = user32.LockWindowUpdate
    lock.argtypes = (wintypes.HWND,)
    lock.restype = wintypes.BOOL
    return bool(lock(wintypes.HWND(as_hwnd(hwnd))))


def unlock_and_repaint(hwnd) -> bool:
    """Release the lock from :func:`lock_window_update` and repaint in one pass."""
    lock = user32.LockWindowUpdate
    lock.argtypes = (wintypes.HWND,)
    lock.restype = wintypes.BOOL
    lock(None)
    return sync_redraw_all(hwnd)


def erase_subclass_state(hwnd) -> dict:
    """Report whether the ``WM_ERASEBKGND`` subclass is still installed.

    Installing a window-procedure subclass is only half the experiment: Tk (or
    anything else) can reset ``GWLP_WNDPROC`` afterwards and silently drop it, in
    which case a "suppressing the erase changes nothing" result means nothing at
    all. This lets a run prove the subclass was live.
    """
    hwnd = as_hwnd(hwnd)
    entry = _subclassed.get(hwnd)
    if not entry:
        return {"installed": False, "still_current": False, "erase_count": 0}
    callback, _previous, counters = entry
    get_long = user32.GetWindowLongPtrW
    get_long.argtypes = (wintypes.HWND, ctypes.c_int)
    get_long.restype = ctypes.c_ssize_t
    current = get_long(wintypes.HWND(hwnd), GWLP_WNDPROC)
    ours = ctypes.cast(callback, ctypes.c_void_p).value
    return {
        "installed": True,
        "still_current": bool(current) and current == ours,
        "erase_count": counters["erase"],
    }


# --------------------------------------------------------------------------- #
# Message spy
# --------------------------------------------------------------------------- #

# Only the messages that can move, show or repaint a window.  The spy runs *inside*
# the window procedure, so every message it touches is a message the app handles
# more slowly - log the whole stream and the instrument changes the thing it
# measures.  WM_PAINT is included deliberately: knowing *when* the toplevel paints
# is the point.
#
# WM_TIMER (0x0113) is the one that answers "is something driving a repaint loop?" -
# a `after()`/`SetTimer` poll that invalidates the window shows up here and nowhere
# else.  Note the limit: Tk's own notifier timer is created with a NULL hwnd, so it
# is posted to the *thread* and never reaches any window procedure.  A zero
# WM_TIMER count therefore does not prove there is no timer - see
# `diag_idle_paint.py`, which tests the same question from the CPU side.
_SPY_MESSAGES = {
    0x0005: "WM_SIZE",
    0x0006: "WM_ACTIVATE",
    0x000F: "WM_PAINT",
    0x0014: "WM_ERASEBKGND",
    0x0018: "WM_SHOWWINDOW",
    0x001C: "WM_ACTIVATEAPP",
    0x0024: "WM_GETMINMAXINFO",
    0x0046: "WM_WINDOWPOSCHANGING",
    0x0047: "WM_WINDOWPOSCHANGED",
    0x0083: "WM_NCCALCSIZE",
    0x0085: "WM_NCPAINT",
    0x0112: "WM_SYSCOMMAND",
    0x0113: "WM_TIMER",
}


def spy_window_messages(hwnd, log_path: str | None = None) -> bool:
    """Log the toplevel's own messages, with an absolute epoch, to ``log_path``.

    This answers the question a frame timeline cannot: *who* started the repaint.
    If ``WM_SIZE`` or ``WM_WINDOWPOSCHANGED`` arrive just before the blank, Windows
    asked the app to re-layout and the app complied - fixable in the app.  If
    nothing arrives and the blank still happens, the repaint is the toolkit's own -
    not fixable in the app.  Those two have completely different fixes and no amount
    of measuring pixels tells them apart.

    ``WM_PAINT`` is logged too, so the parent's paint can be placed against the
    moment the screen went blank.

    Pass ``log_path=None`` to install the same subclass with **counters only**.  That
    matters when the spy's own cost is under measurement: a line-buffered write per
    message is I/O the app did not ask for, and it lands in exactly the CPU figures
    the caller is trying to attribute.  Read the counters with
    ``spy_message_counts``.
    """
    hwnd = as_hwnd(hwnd)
    if not hwnd:
        return False

    get_long = user32.GetWindowLongPtrW
    get_long.argtypes = (wintypes.HWND, ctypes.c_int)
    get_long.restype = ctypes.c_ssize_t
    set_long = user32.SetWindowLongPtrW
    set_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    set_long.restype = ctypes.c_ssize_t
    call_proc = user32.CallWindowProcW
    call_proc.argtypes = (
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    )
    call_proc.restype = ctypes.c_ssize_t

    previous = get_long(wintypes.HWND(hwnd), GWLP_WNDPROC)
    if not previous:
        return False

    handle = None
    if log_path:
        directory = os.path.dirname(log_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        handle = open(log_path, "w", encoding="utf-8", buffering=1)
        handle.write("# epoch message wparam lparam\n")
    counts: dict[str, int] = {}

    def window_proc(h, message, wparam, lparam):
        name = _SPY_MESSAGES.get(message)
        if name is not None:
            counts[name] = counts.get(name, 0) + 1
            if handle is not None:
                handle.write(f"{time.time():.6f} {name} {wparam} {lparam}\n")
        return call_proc(previous, h, message, wparam, lparam)

    callback = _WNDPROC(window_proc)
    set_long(
        wintypes.HWND(hwnd), GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p).value
    )
    # Keep the thunk alive in the same registry the erase subclass uses, so it is
    # never garbage-collected while Windows still holds a pointer to it.
    _subclassed[hwnd] = (callback, previous, {"erase": 0, "spy": counts})
    return True


def spy_message_counts(hwnd) -> dict:
    """How many of each message the spy has logged so far."""
    entry = _subclassed.get(as_hwnd(hwnd))
    if not entry:
        return {}
    return dict(entry[2].get("spy") or {})


# --------------------------------------------------------------------------- #
# Child-window census
# --------------------------------------------------------------------------- #

GW_CHILD = 5
GW_HWNDNEXT = 2


def child_windows(hwnd) -> list[int]:
    """Every descendant window. ``EnumChildWindows`` is recursive by definition."""
    found: list[int] = []
    proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows.argtypes = (wintypes.HWND, proc_type, wintypes.LPARAM)
    user32.EnumChildWindows.restype = wintypes.BOOL

    def visit(child, _param):
        found.append(as_hwnd(child))
        return True

    callback = proc_type(visit)
    user32.EnumChildWindows(wintypes.HWND(as_hwnd(hwnd)), callback, 0)
    return found


def direct_children(hwnd) -> list[int]:
    """Only the immediate children, in z-order."""
    found: list[int] = []
    child = user32.GetWindow(wintypes.HWND(as_hwnd(hwnd)), GW_CHILD)
    while child:
        found.append(as_hwnd(child))
        child = user32.GetWindow(wintypes.HWND(as_hwnd(child)), GW_HWNDNEXT)
    return found


# --------------------------------------------------------------------------- #
# Process cost
# --------------------------------------------------------------------------- #

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
FILETIME_TICKS_PER_SECOND = 10_000_000


def process_cpu_seconds(pid: int) -> float | None:
    """Total CPU seconds (user + kernel) consumed by ``pid``, or ``None``.

    Why this exists: ``WS_EX_COMPOSITED`` makes DWM composite the window from a
    back buffer, and on a window with 118 child windows that is the one documented
    way it can cost real performance.  "Does this fix make the app work harder?" is
    not answerable from frame captures - a slower app presents the *same* frames,
    just later - so measure the process's own CPU time instead.

    Returns wall-clock-independent CPU seconds, so a variant can be compared
    against a baseline that ran for a different length of time.
    """
    if os.name != "nt" or not pid:
        return None
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    _kernel32.GetProcessTimes.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL

    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not _kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None

        def ticks(value) -> int:
            return (value.dwHighDateTime << 32) | value.dwLowDateTime

        return round((ticks(kernel) + ticks(user)) / FILETIME_TICKS_PER_SECOND, 4)
    finally:
        _kernel32.CloseHandle(handle)
