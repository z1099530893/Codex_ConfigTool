"""Do the close paths that WS_SYSMENU newly exposes shut the app down cleanly?

Adding ``WS_SYSMENU`` (so the Shell will treat the window as minimizable) also
makes ``SC_CLOSE`` reachable: Alt+F4, the system menu's Close item, and the
taskbar jump list's Close entry.  Before that bit was set the window had no
system menu at all, so those paths did not exist - which means enabling them is a
behaviour change that has to be checked, not assumed.

The custom close button calls ``self.destroy()``, and so does the pre-existing
Alt+F4 binding, so ``WM_CLOSE`` should land on exactly the same path.  What this
checks is that the whole process tree actually goes away, rather than the window
merely disappearing while the single-instance mutex stays held.

Usage:
    python diag_close_paths.py
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import winapi as W  # noqa: E402
from accept_packaged_exe import (  # noqa: E402
    all_visible_windows,
    find_main_window,
    process_alive,
)

user32 = ctypes.windll.user32
WM_CLOSE = 0x0010
WM_SYSCOMMAND = 0x0112
SC_CLOSE = 0xF060

user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.SendMessageW.restype = ctypes.c_void_p
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL

EXE = os.path.join(ROOT, "dist", "CodexConfigTool.exe")


def tasklist_lines(exe_name: str) -> list[str]:
    """Rows of ``tasklist`` for one image name, or [] when it cannot be read."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in (result.stdout or "").splitlines() if line.strip()]


def pids_of(exe_name: str) -> list[int]:
    """Every live PID whose executable basename matches (the --onefile bootloader
    and the real app process are separate PIDs)."""
    pids = []
    for line in tasklist_lines(exe_name):
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == exe_name.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def raw_tasklist(exe_name: str) -> str:
    return "\n".join(tasklist_lines(exe_name)) or "(no output)"


def run_case(label: str, send) -> dict:
    exe_name = os.path.basename(EXE)
    pre = set(all_visible_windows())
    process = subprocess.Popen([EXE], cwd=ROOT)
    hwnd, pid = find_main_window(pre)
    if not hwnd:
        return {"case": label, "ok": False, "detail": "main window not found"}
    time.sleep(2.5)
    style = W.get_style(hwnd)
    entry: dict = {
        "case": label,
        "hwnd": hex(hwnd),
        "pid": pid,
        "WS_SYSMENU": bool(style & W.WS_SYSMENU),
        "system_menu": (W.system_menu_report(hwnd) or {}).get("items", {}).get("Close"),
    }

    started = time.time()
    send(hwnd)
    # Poll for a clean exit: both the window and every process of the tree.
    deadline = time.time() + 15.0
    window_gone_at = None
    process_gone_at = None
    leftover: list[int] = []
    while time.time() < deadline:
        if window_gone_at is None and not W.user32.IsWindow(wintypes.HWND(hwnd)):
            window_gone_at = round(time.time() - started, 2)
        if process_gone_at is None and not process_alive(pid):
            process_gone_at = round(time.time() - started, 2)
        leftover = pids_of(exe_name)
        if window_gone_at is not None and process_gone_at is not None and not leftover:
            break
        time.sleep(0.25)

    entry["window_gone_after"] = window_gone_at
    entry["process_gone_after"] = process_gone_at
    entry["leftover_pids"] = leftover
    entry["tasklist"] = raw_tasklist(exe_name) if leftover else ""
    entry["ok"] = bool(window_gone_at is not None and process_gone_at is not None and not leftover)
    if not entry["ok"]:
        entry["detail"] = (
            f"window_gone={window_gone_at} process_gone={process_gone_at} leftover={leftover}"
        )
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
    return entry


def main() -> int:
    if not os.path.exists(EXE):
        print(f"ENVIRONMENT missing {EXE}")
        return 3

    results = [
        run_case("WM_CLOSE (system menu Close / Alt+F4 equivalent)",
                 lambda h: user32.PostMessageW(wintypes.HWND(h), WM_CLOSE, 0, 0)),
        run_case("WM_SYSCOMMAND / SC_CLOSE (jump list Close)",
                 lambda h: user32.PostMessageW(wintypes.HWND(h), WM_SYSCOMMAND, SC_CLOSE, 0)),
    ]

    for entry in results:
        print("[case] " + json.dumps(entry, ensure_ascii=False))
    failures = [e["case"] for e in results if not e["ok"]]
    verdict = "PASS" if not failures else "FAIL"
    print("SUMMARY " + json.dumps({"verdict": verdict, "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
