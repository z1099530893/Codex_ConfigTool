"""Probe the desktop's input state to explain why taskbar clicks are ignored.

Checks cursor movement, mouse capture, and the foreground thread's GUI state
(``GetGUIThreadInfo``), which reveals a stuck capture, a modal menu loop, or a
move/size loop that would swallow synthetic clicks aimed at the taskbar.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

import winapi as W

user32 = ctypes.windll.user32


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


user32.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(GUITHREADINFO))
user32.GetGUIThreadInfo.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.GetCapture.argtypes = ()
user32.GetCapture.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetLastInputInfo.argtypes = (ctypes.c_void_p,)


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def describe(hwnd) -> str:
    hwnd = W.as_hwnd(hwnd)
    if not hwnd:
        return "0"
    return f"{hwnd:#x} class={W.class_name(hwnd)!r} title={W.window_text(hwnd)[:30]!r}"


def main() -> int:
    print("screen", W.user32.GetSystemMetrics(0), "x", W.user32.GetSystemMetrics(1))
    print("taskbar", W.window_rect(W.user32.FindWindowW("Shell_TrayWnd", None)))
    print("GetCapture:", describe(user32.GetCapture()))

    for x, y in ((1562, 1060), (20, 1060), (960, 540)):
        user32.SetCursorPos(x, y)
        time.sleep(0.25)
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        print(f"\nrequested ({x},{y}) -> actual ({point.x},{point.y})")
        print(f"  WindowFromPoint: {describe(W.window_at(point.x, point.y))}")
        print(f"  root:            {describe(W.root_at(point.x, point.y))}")

    foreground = W.as_hwnd(user32.GetForegroundWindow())
    print("\nforeground:", describe(foreground))
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    thread = user32.GetWindowThreadProcessId(wintypes.HWND(foreground), None)
    if user32.GetGUIThreadInfo(thread, ctypes.byref(info)):
        print(f"  flags={info.flags:#x}")
        print("  hwndActive:    ", describe(info.hwndActive))
        print("  hwndFocus:     ", describe(info.hwndFocus))
        print("  hwndCapture:   ", describe(info.hwndCapture))
        print("  hwndMenuOwner: ", describe(info.hwndMenuOwner))
        print("  hwndMoveSize:  ", describe(info.hwndMoveSize))
    else:
        print("  GetGUIThreadInfo failed")

    current = W.as_hwnd(user32.GetForegroundWindow())
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    thread = W._kernel32.GetCurrentThreadId()
    if user32.GetGUIThreadInfo(thread, ctypes.byref(info)):
        print(f"\ncurrent thread ({thread}) GUI info:")
        print("  hwndCapture:   ", describe(info.hwndCapture))
        print("  hwndMenuOwner: ", describe(info.hwndMenuOwner))
        print("  hwndMoveSize:  ", describe(info.hwndMoveSize))

    last = LASTINPUTINFO()
    last.cbSize = ctypes.sizeof(LASTINPUTINFO)
    user32.GetLastInputInfo(ctypes.byref(last))
    print(f"\nlast input tick={last.dwTime} uptime={W._kernel32.GetTickCount()}")
    print(f"current foreground again: {describe(current)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
