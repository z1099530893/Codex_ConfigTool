"""Screen / window capture helper for automated window-lifecycle validation.

Uses ctypes + GDI (BitBlt) so it does not depend on any third-party screenshot
binary.  PIL is only used to save the resulting image.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.GetDC.argtypes = (wintypes.HWND,)
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
user32.ReleaseDC.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
user32.GetWindowRect.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = (
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
)
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = (
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.UINT,
)
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = (wintypes.HDC,)
gdi32.DeleteDC.restype = wintypes.BOOL

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def grab_rect(x: int, y: int, width: int, height: int) -> Image.Image:
    """Capture an arbitrary screen rectangle."""
    width = max(int(width), 1)
    height = max(int(height), 1)
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    previous = gdi32.SelectObject(mem_dc, bitmap)
    gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, int(x), int(y), SRCCOPY | CAPTUREBLT)

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height  # top-down
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0

    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0)

    image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")

    gdi32.SelectObject(mem_dc, previous)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)
    return image


def primary_size() -> tuple[int, int]:
    return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def grab_primary_screen(scale_width: int | None = None) -> Image.Image:
    width, height = primary_size()
    image = grab_rect(0, 0, width, height)
    if scale_width and width > scale_width:
        ratio = scale_width / width
        image = image.resize((scale_width, max(int(height * ratio), 1)), Image.LANCZOS)
    return image


def taskbar_rect() -> tuple[int, int, int, int]:
    """Return the primary taskbar rect as (left, top, width, height)."""
    tray = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
    if tray:
        rect = wintypes.RECT()
        if user32.GetWindowRect(wintypes.HWND(tray), ctypes.byref(rect)):
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width > 0 and height > 0:
                return (rect.left, rect.top, width, height)
    width, screen_height = primary_size()
    return (0, screen_height - 56, width, 56)


def grab_taskbar_strip(height: int = 56) -> Image.Image:
    """Capture the real taskbar, located via its own window rect.

    Using ``Shell_TrayWnd``'s rect avoids the DPI/virtual-screen offset problems
    that come from guessing ``screen_height - height``.  Remember that strip
    coordinates are *relative to the taskbar*, so add :func:`taskbar_rect`'s
    origin before clicking anything found in the image.
    """
    left, top, width, height = taskbar_rect()
    return grab_rect(left, top, width, height)


def grab_window(hwnd: int, margin: int = 0) -> Image.Image:
    """Capture the window's screen area, including whatever is behind it."""
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        raise OSError("GetWindowRect failed for hwnd %s" % hwnd)
    return grab_rect(
        rect.left - margin,
        rect.top - margin,
        (rect.right - rect.left) + margin * 2,
        (rect.bottom - rect.top) + margin * 2,
    )


def taskbar_button_area_right_edge(image: Image.Image, scan: tuple[int, int] = (230, 1655)) -> int:
    """Return the rightmost x (within ``scan``) that is not taskbar background.

    The Windows 10 taskbar lays task buttons out left-aligned, so a window that
    owns a taskbar button pushes this edge to the right by roughly one button
    width (~160 px).  This is far more robust than a raw pixel diff, because it
    ignores the clock and the notification tray, which are outside ``scan``.
    """
    width, height = image.size
    row = height // 2
    left, right = max(scan[0], 0), min(scan[1], width - 1)
    counts: dict[tuple[int, int, int], int] = {}
    for x in range(left, right + 1):
        pixel = image.getpixel((x, row))
        counts[pixel] = counts.get(pixel, 0) + 1
    background = max(counts.items(), key=lambda item: item[1])[0]

    def is_background(pixel: tuple[int, int, int]) -> bool:
        return all(abs(pixel[i] - background[i]) <= 6 for i in range(3))

    edge = left
    for x in range(left, right + 1):
        if not is_background(image.getpixel((x, row))):
            edge = x
    return edge


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--hwnd", type=int, default=None)
    parser.add_argument("--margin", type=int, default=0)
    parser.add_argument("--taskbar", action="store_true")
    args = parser.parse_args()

    if args.taskbar:
        image = grab_taskbar_strip()
    elif args.hwnd:
        image = grab_window(args.hwnd, args.margin)
    else:
        image = grab_primary_screen()
    image.save(args.out)
    print("saved %s %sx%s" % (args.out, image.width, image.height))


if __name__ == "__main__":
    main()
