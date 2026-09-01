from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility
    tomllib = None


APP_NAME = "Codex 配置助手"
APP_VERSION = "1.4.0"
AUTHOR_NAME = "k.x"
CONTACT_EMAIL = "1099530893@qq.com"
PROJECT_URL = "https://github.com/z1099530893/Codex_ConfigTool"
LATEST_RELEASE_PAGE_URL = f"{PROJECT_URL}/releases/latest"
RECOMMENDED_CHANNEL_URL = "https://ai.arkapi.top"
JM2API_CHANNEL_URL = "https://jm2api.lol"
DONATION_THUMBNAIL_IMAGE_NAME = "donation_105.png"
DONATION_DIALOG_IMAGE_NAME = "donation_210.png"
APP_ICON_PNG_NAME = "app_icon.png"
ARKAPI_ICON_NAME = "arkapi.png"
JM2API_ICON_NAME = "jm2api.png"
APP_ICON_ICO_NAME = "app_icon.ico"
TITLE_ICON_PNG_NAME = "app_icon_title.png"
TITLE_ABOUT_ICON_NAME = "title_about.png"
TITLE_MINIMIZE_ICON_NAME = "title_minimize.png"
TITLE_CLOSE_ICON_NAME = "title_close.png"
EYE_ICON_NAME = "eye_smooth.png"
EYE_OFF_ICON_NAME = "eye_off_smooth.png"
ABOUT_MARK_PNG_NAME = "app_icon_about.png"
WINDOW_WIDTH = 820
WINDOW_HEIGHT = 500
STATUS_AREA_HEIGHT = 32
DEFAULT_PROVIDER = "openai"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_CUSTOM_PROVIDER = "custom"
TEMPLATE_PROVIDER_ID = "newapi"
TEMPLATE_MODEL = "gpt-5.4"
TEMPLATE_PROVIDER_NAME = "openai"
TEMPLATE_BASE_URL = DEFAULT_BASE_URL
MAX_BACKUP_NAME_LENGTH = 40
BACKUP_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
BACKUP_DIR_PATTERN = re.compile(r"^(?P<timestamp>\d{8}-\d{6})-(?P<name>.+)$")
SETTINGS_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "CodexConfigTool"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
OFFICIAL_LOGIN_MODE_PATH_KEY = "official_login_mode_path"
HIDE_ONBOARDING_KEY = "hide_onboarding"
ONBOARDING_SHOWN_KEY = "onboarding_shown"
SINGLE_INSTANCE_MUTEX_NAME = "Local\\z1099530893.CodexConfigTool"
ERROR_ALREADY_EXISTS = 183
PROFILE_CACHE_LIMIT = 512
MODEL_LIST_TIMEOUT_SECONDS = 8.0
MODEL_LIST_MAX_BYTES = 2 * 1024 * 1024
MODEL_LIST_MAX_ITEMS = 5000
MODEL_ID_MAX_LENGTH = 256
MODEL_DISPLAY_NAME_MAX_LENGTH = 80
MODEL_CATALOG_FILENAME = "codex-config-tool-model-catalog.json"
CODEX_NATIVE_MODEL_CACHE_FILENAME = "models_cache.json"
MODEL_CATALOG_REASONING_LEVELS = (
    ("low", "Low reasoning effort"),
    ("medium", "Medium reasoning effort"),
    ("high", "High reasoning effort"),
    ("xhigh", "Extra high reasoning effort"),
)
MANAGED_CONFIG_FILE_NAMES = ("auth.json", "config.toml", MODEL_CATALOG_FILENAME)
UPDATE_CHECK_TIMEOUT_SECONDS = 6.0
CODEX_TRAY_SHELL_SETTLE_SECONDS = 3.0
CODEX_NORMAL_EXIT_TIMEOUT_SECONDS = 15.0
CODEX_FOREGROUND_SETTLE_SECONDS = 0.4
CODEX_KEYSTROKE_INTERVAL_SECONDS = 0.04
CODEX_START_TIMEOUT_SECONDS = 15.0
CODEX_STORE_PACKAGE_FAMILY = "OpenAI.Codex_2p2nqsd0c76g0"
CODEX_STORE_PROD_TRAY_GUID = "e5768d8b-6936-4f45-b1ad-4c5fb414cb35"
CODEX_PACKAGE_PATH_PATTERN = re.compile(
    r"[\\/]WindowsApps[\\/](?P<identity>OpenAI\.Codex)_[^\\/]+__(?P<publisher>[^\\/]+)[\\/]",
    re.IGNORECASE,
)


def horizontal_drag_scroll_units(pointer_x: int, entry_width: int) -> int:
    """Return accelerated horizontal scroll units when dragging beyond an entry."""
    if entry_width <= 0:
        return 0
    if pointer_x < 0:
        distance = -pointer_x
        direction = -1
    elif pointer_x >= entry_width:
        distance = pointer_x - entry_width + 1
        direction = 1
    else:
        return 0
    return direction * min(16, 2 + distance // 8)


def horizontal_scroll_target(
    first: float,
    last: float,
    viewport_width: int,
    pixel_delta: float,
) -> float:
    """Translate a pixel scroll distance into a clamped Entry xview position."""
    span = max(last - first, 0.0)
    if viewport_width <= 0 or span <= 0.0 or span >= 1.0:
        return 0.0
    content_width = viewport_width / span
    return min(max(first + pixel_delta / content_width, 0.0), 1.0 - span)


def register_appwindow_with_shell(hwnd: int, user32=None) -> None:
    """Apply taskbar styles and notify Windows about a borderless window's frame change."""
    if os.name != "nt" and user32 is None:
        return
    if user32 is None:
        import ctypes

        user32 = ctypes.windll.user32
    extended_style = user32.GetWindowLongW(hwnd, -20)
    extended_style = (extended_style & ~0x00000080) | 0x00040000
    user32.SetWindowLongW(hwnd, -20, extended_style)
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)  # NOMOVE | NOSIZE | NOZORDER | FRAMECHANGED


def resource_path(name: str) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / "assets" / name


def acquire_single_instance(name: str = SINGLE_INSTANCE_MUTEX_NAME) -> int | None:
    if os.name != "nt":
        return -1
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_bool
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return int(handle)


def release_single_instance(handle: int | None) -> None:
    if os.name != "nt" or handle in (None, -1):
        return
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_bool
    kernel32.CloseHandle(handle)


def show_already_running_message() -> None:
    if os.name != "nt":
        return
    import ctypes

    ctypes.windll.user32.MessageBoxW(
        None,
        "Codex 配置助手已经在运行，请先使用已打开的窗口。",
        APP_NAME,
        0x00000040,
    )


class CodexRestartError(RuntimeError):
    pass


class UpdateCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    page_url: str


@dataclass(frozen=True)
class CodexLaunchResult:
    target: CodexRestartTarget
    action: str


def version_tuple(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip(), re.IGNORECASE)
    if not match:
        raise UpdateCheckError("Release 版本号格式无效。")
    return tuple(int(part) for part in match.groups())


def parse_latest_release_url(release_url: str, current_version: str = APP_VERSION) -> UpdateInfo | None:
    parsed = urllib.parse.urlsplit(release_url)
    expected_prefix = "/z1099530893/Codex_ConfigTool/releases/tag/"
    if parsed.scheme != "https" or parsed.hostname != "github.com" or not parsed.path.startswith(expected_prefix):
        raise UpdateCheckError("更新服务返回的 Release 地址无效。")
    tag_name = urllib.parse.unquote(parsed.path[len(expected_prefix) :]).strip("/")
    if version_tuple(tag_name) <= version_tuple(current_version):
        return None
    version = tag_name.removeprefix("v").removeprefix("V")
    return UpdateInfo(version=version, page_url=f"{PROJECT_URL}/releases/tag/{tag_name}")


def fetch_latest_release(timeout: float = UPDATE_CHECK_TIMEOUT_SECONDS) -> UpdateInfo | None:
    request = urllib.request.Request(
        LATEST_RELEASE_PAGE_URL,
        headers={
            "Accept": "text/html",
            "User-Agent": f"CodexConfigTool/{APP_VERSION}",
        },
        method="HEAD",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            release_url = response.geturl()
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 303, 307, 308):
            raise UpdateCheckError(f"更新服务返回 HTTP {exc.code}。") from exc
        release_url = exc.headers.get("Location", "")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateCheckError("暂时无法连接更新服务。") from exc
    return parse_latest_release_url(release_url)


def list_windows_processes(executable_names: set[str]) -> list[ProcessRecord]:
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    records = []
    wanted = {name.casefold() for name in executable_names}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        has_entry = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
        while has_entry:
            if entry.szExeFile.casefold() in wanted:
                process = kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)
                if process:
                    try:
                        capacity = wintypes.DWORD(32768)
                        buffer = ctypes.create_unicode_buffer(capacity.value)
                        if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(capacity)):
                            records.append(
                                ProcessRecord(
                                    pid=int(entry.th32ProcessID),
                                    parent_pid=int(entry.th32ParentProcessID),
                                    executable=Path(buffer.value),
                                )
                            )
                    finally:
                        kernel32.CloseHandle(process)
            has_entry = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)
    return records


def codex_restart_target(processes: list[ProcessRecord]) -> CodexRestartTarget | None:
    main_processes = []
    for process in processes:
        executable_name = process.executable.name.casefold()
        executable_text = str(process.executable).casefold().replace("/", "\\")
        is_codex_install = "openai.codex_" in executable_text or "\\codex\\" in executable_text
        if executable_name in {"chatgpt.exe", "codex.exe"} and is_codex_install:
            main_processes.append(process)
    if not main_processes:
        return None

    process_ids = {process.pid for process in main_processes}
    roots = [process for process in main_processes if process.parent_pid not in process_ids]
    preferred = roots or main_processes
    preferred.sort(key=lambda process: (process.executable.name.casefold() != "chatgpt.exe", process.pid))
    root = preferred[0]

    package_match = CODEX_PACKAGE_PATH_PATTERN.search(str(root.executable))
    app_user_model_id = None
    if package_match:
        app_user_model_id = f"{package_match.group('identity')}_{package_match.group('publisher')}!App"
    return CodexRestartTarget(
        root_pid=root.pid,
        executable=root.executable,
        app_user_model_id=app_user_model_id,
    )


def discover_codex_installation() -> CodexRestartTarget | None:
    """Find a launchable Codex installation when no Codex process is running."""
    if os.name != "nt":
        return None

    app_user_model_id = ""
    powershell_script = (
        "$package = Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue | "
        "Select-Object -First 1; "
        "if ($package) { "
        "$manifest = Get-AppxPackageManifest -Package $package.PackageFullName "
        "-ErrorAction SilentlyContinue; "
        "$application = @($manifest.Package.Applications.Application) | Select-Object -First 1; "
        "if ($application) { Write-Output ($package.PackageFamilyName + '!' + $application.Id) } "
        "}; "
        "if (-not $application) { "
        "$startApp = Get-StartApps | Where-Object { $_.AppID -like 'OpenAI.Codex_*!*' } | "
        "Select-Object -First 1; "
        "if ($startApp) { Write-Output $startApp.AppID } "
        "}"
    )
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                powershell_script,
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        for line in completed.stdout.splitlines():
            candidate = line.strip()
            if re.fullmatch(r"OpenAI\.Codex_[^!\s]+![^!\s]+", candidate, re.IGNORECASE):
                app_user_model_id = candidate
                break
    except OSError:
        pass
    if app_user_model_id:
        return CodexRestartTarget(
            root_pid=0,
            executable=Path(),
            app_user_model_id=app_user_model_id,
        )

    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", ""))
    candidates = (
        local_app_data / "Programs" / "Codex" / "Codex.exe",
        local_app_data / "Programs" / "OpenAI" / "Codex" / "Codex.exe",
        program_files / "Codex" / "Codex.exe",
        program_files / "OpenAI" / "Codex" / "Codex.exe",
    )
    for executable in candidates:
        if executable.is_file():
            return CodexRestartTarget(root_pid=0, executable=executable)
    return None


def codex_app_process_ids(processes: list[ProcessRecord], target: CodexRestartTarget) -> set[int]:
    """Return only desktop host processes belonging to the selected Codex installation."""
    if target.app_user_model_id:
        return {
            process.pid
            for process in processes
            if process.executable.name.casefold() in {"chatgpt.exe", "codex.exe"}
            and "openai.codex_" in str(process.executable).casefold().replace("/", "\\")
        }
    target_path = str(target.executable).casefold()
    return {
        process.pid
        for process in processes
        if str(process.executable).casefold() == target_path
    }


def wait_for_codex_app_exit(target: CodexRestartTarget, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        processes = list_windows_processes({"ChatGPT.exe", "Codex.exe"})
        if not codex_app_process_ids(processes, target):
            return True
        time.sleep(0.1)
    processes = list_windows_processes({"ChatGPT.exe", "Codex.exe"})
    return not codex_app_process_ids(processes, target)


def request_codex_normal_exit(target: CodexRestartTarget) -> bool:
    """Use Codex's own Ctrl+Q menu accelerator, which invokes Electron app.quit()."""
    processes = list_windows_processes({"ChatGPT.exe", "Codex.exe"})
    matching_ids = codex_app_process_ids(processes, target)
    if not matching_ids:
        return True
    if not send_codex_quit_shortcut(matching_ids):
        return False
    return wait_for_codex_app_exit(target, CODEX_NORMAL_EXIT_TIMEOUT_SECONDS)


def windows_keyboard_input_types():
    """Return ABI-complete Win32 INPUT types; its union size is platform-sensitive."""
    import ctypes
    from ctypes import wintypes

    class MouseInput(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.WPARAM),
        )

    class KeyboardInput(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", wintypes.WPARAM),
        )

    class HardwareInput(ctypes.Structure):
        _fields_ = (
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        )

    class InputUnion(ctypes.Union):
        _fields_ = (
            ("mi", MouseInput),
            ("ki", KeyboardInput),
            ("hi", HardwareInput),
        )

    class Input(ctypes.Structure):
        _anonymous_ = ("value",)
        _fields_ = (("type", wintypes.DWORD), ("value", InputUnion))

    return KeyboardInput, Input


def send_codex_quit_shortcut(process_ids: set[int]) -> bool:
    """Focus a verified Codex window and send its registered Ctrl+Q accelerator."""
    if os.name != "nt" or not process_ids:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND

    windows: list[tuple[bool, int]] = []

    @callback_type
    def collect_window(hwnd, _lparam):
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if int(process_id.value) in process_ids:
            windows.append((bool(user32.IsWindowVisible(hwnd)), int(hwnd)))
        return True

    user32.EnumWindows(collect_window, 0)
    if not windows:
        return False
    windows.sort(reverse=True)
    hwnd = windows[0][1]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if not user32.SetForegroundWindow(hwnd):
        return False

    # SetForegroundWindow returns before Electron necessarily finishes processing
    # activation. Wait until the verified Codex window has settled before typing.
    focus_deadline = time.monotonic() + 2.0
    while True:
        foreground_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(foreground_pid))
        if int(foreground_pid.value) in process_ids:
            break
        if time.monotonic() >= focus_deadline:
            return False
        time.sleep(0.05)
    time.sleep(CODEX_FOREGROUND_SETTLE_SECONDS)

    foreground_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(foreground_pid))
    if int(foreground_pid.value) not in process_ids:
        return False

    KeyboardInput, Input = windows_keyboard_input_types()

    key_up = 0x0002
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT

    def send_key(virtual_key: int, flags: int = 0) -> bool:
        key_input = Input(type=1, ki=KeyboardInput(wVk=virtual_key, dwFlags=flags))
        return user32.SendInput(1, ctypes.byref(key_input), ctypes.sizeof(Input)) == 1

    control_down = False
    try:
        control_down = send_key(0x11)  # VK_CONTROL down
        if not control_down:
            return False
        time.sleep(CODEX_KEYSTROKE_INTERVAL_SECONDS)
        if not send_key(ord("Q")):
            return False
        time.sleep(CODEX_KEYSTROKE_INTERVAL_SECONDS)
        if not send_key(ord("Q"), key_up):
            return False
        time.sleep(CODEX_KEYSTROKE_INTERVAL_SECONDS)
        return send_key(0x11, key_up)
    finally:
        if control_down:
            # A failed partial sequence must never leave Ctrl logically pressed.
            send_key(0x11, key_up)


def codex_tray_guid(target: CodexRestartTarget) -> str | None:
    app_user_model_id = (target.app_user_model_id or "").casefold()
    if app_user_model_id.startswith(f"{CODEX_STORE_PACKAGE_FAMILY}!".casefold()):
        return CODEX_STORE_PROD_TRAY_GUID
    return None


def remove_stale_codex_tray_registration(target: CodexRestartTarget) -> bool:
    """Remove only Codex's fixed Store tray GUID after its old host has exited."""
    tray_guid = codex_tray_guid(target)
    if os.name != "nt" or tray_guid is None:
        return False
    import ctypes
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = (
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        )

    class NotifyIconData(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HANDLE),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", Guid),
            ("hBalloonIcon", wintypes.HANDLE),
        )

    parsed_guid = uuid.UUID(tray_guid)
    data = NotifyIconData()
    data.cbSize = ctypes.sizeof(NotifyIconData)
    data.uFlags = 0x00000020  # NIF_GUID
    data.guidItem = Guid(
        parsed_guid.time_low,
        parsed_guid.time_mid,
        parsed_guid.time_hi_version,
        (ctypes.c_ubyte * 8)(*parsed_guid.bytes[8:]),
    )
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.Shell_NotifyIconW.argtypes = (
        wintypes.DWORD,
        ctypes.POINTER(NotifyIconData),
    )
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    return bool(shell32.Shell_NotifyIconW(0x00000002, ctypes.byref(data)))  # NIM_DELETE


def wait_for_new_codex_process(
    target: CodexRestartTarget,
    previous_process_ids: set[int],
    timeout: float = CODEX_START_TIMEOUT_SECONDS,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        processes = list_windows_processes({"ChatGPT.exe", "Codex.exe"})
        if codex_app_process_ids(processes, target) - previous_process_ids:
            return True
        time.sleep(0.1)
    processes = list_windows_processes({"ChatGPT.exe", "Codex.exe"})
    return bool(codex_app_process_ids(processes, target) - previous_process_ids)


def activate_codex_window(target: CodexRestartTarget, timeout: float = 12.0) -> bool:
    """Wait for the launched Codex window and bring it back to the foreground."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL

    def process_ids() -> set[int]:
        records = list_windows_processes({"ChatGPT.exe", "codex.exe"})
        if target.app_user_model_id:
            return {
                record.pid
                for record in records
                if "openai.codex_" in str(record.executable).casefold().replace("/", "\\")
            }
        return {
            record.pid
            for record in records
            if str(record.executable).casefold() == str(target.executable).casefold()
        }

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        candidate_ids = process_ids()
        found = {"handle": 0}

        @callback_type
        def find_window(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if int(process_id.value) in candidate_ids:
                found["handle"] = hwnd
                return False
            return True

        user32.EnumWindows(find_window, 0)
        if found["handle"]:
            user32.ShowWindow(found["handle"], 9)  # SW_RESTORE
            user32.SetForegroundWindow(found["handle"])
            return True
        time.sleep(0.2)
    return False


def launch_codex_target(target: CodexRestartTarget) -> None:
    if target.app_user_model_id:
        # Route packaged-app activation through the user's Windows shell. A direct
        # COM activation makes Codex a child of this helper, so closing the helper
        # can also end Codex and its tray controller.
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{target.app_user_model_id}"],
            close_fds=True,
        )
        return
    subprocess.Popen(
        [str(target.executable)],
        close_fds=True,
        creationflags=(
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        ),
    )


def is_codex_application_running() -> bool:
    if os.name != "nt":
        return False
    processes = list_windows_processes({"ChatGPT.exe", "codex.exe", "codex-code-mode-host.exe"})
    return codex_restart_target(processes) is not None


def launch_codex_application(target: CodexRestartTarget, action: str) -> CodexLaunchResult:
    previous_processes = list_windows_processes({"ChatGPT.exe", "Codex.exe"})
    previous_process_ids = codex_app_process_ids(previous_processes, target)
    launched_target = target
    if action == "restart":
        # Electron reuses a fixed tray GUID. Give Explorer time to remove the old
        # registration before the new process creates its tray controller.
        time.sleep(CODEX_TRAY_SHELL_SETTLE_SECONDS)
    try:
        launch_codex_target(target)
    except OSError as exc:
        raise CodexRestartError(f"Codex 已关闭，但重新启动失败：{exc}") from exc
    if not wait_for_new_codex_process(target, previous_process_ids):
        if not target.app_user_model_id or not target.executable.is_file():
            raise CodexRestartError("Windows 已接收启动请求，但没有检测到新的 Codex 主进程。")
        launched_target = CodexRestartTarget(root_pid=0, executable=target.executable)
        try:
            launch_codex_target(launched_target)
        except OSError as exc:
            raise CodexRestartError(f"Codex 系统入口启动失败，EXE 回退启动也失败：{exc}") from exc
        if not wait_for_new_codex_process(launched_target, previous_process_ids):
            raise CodexRestartError("Windows 系统入口和 EXE 回退均未启动 Codex 主进程。")
    if not activate_codex_window(launched_target):
        raise CodexRestartError("Codex 进程已启动，但主窗口未显示。请在任务栏或开始菜单中手动打开 Codex。")
    return CodexLaunchResult(target=launched_target, action=action)


def restart_codex_application(target: CodexRestartTarget | None = None) -> CodexLaunchResult:
    if os.name != "nt":
        raise CodexRestartError("重启 Codex 目前仅支持 Windows。")
    if target is None:
        processes = list_windows_processes({"ChatGPT.exe", "codex.exe", "codex-code-mode-host.exe"})
        target = codex_restart_target(processes)
    action = "restart"
    if target is None:
        target = discover_codex_installation()
        if target is None:
            raise CodexRestartError("没有检测到 Codex 安装，也没有正在运行的 Codex。")
        action = "start"
    else:
        installed_target = discover_codex_installation()
        if installed_target is not None and installed_target.app_user_model_id:
            target = CodexRestartTarget(
                root_pid=target.root_pid,
                executable=target.executable,
                app_user_model_id=installed_target.app_user_model_id,
            )
        if not request_codex_normal_exit(target):
            raise CodexRestartError(
                "无法让 Codex 正常退出。请从系统托盘右键退出 Codex 后重试。"
            )
        remove_stale_codex_tray_registration(target)

    return launch_codex_application(target, action)


class Tooltip:
    def __init__(self, widget: tk.Misc, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self.job: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def update_text(self, text: str) -> None:
        self.text = text

    def _schedule(self, _event=None) -> None:
        self._hide()
        self.job = self.widget.after(450, self._show)

    def _show(self) -> None:
        self.job = None
        if not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        transparent_bg = "#f3f4f7" if os.name == "nt" else self.widget.winfo_toplevel().cget("bg")
        self.window.configure(bg=transparent_bg)
        if os.name == "nt":
            try:
                self.window.attributes("-transparentcolor", transparent_bg)
            except tk.TclError:
                pass
        # Keep hover hints deliberately flat: only the text is visible.
        tk.Label(
            self.window,
            text=self.text,
            bg=transparent_bg,
            fg="#111111",
            padx=1,
            pady=1,
            font=("Microsoft YaHei UI", 9),
        ).pack()
        self.window.update_idletasks()
        self.window.geometry(f"+{x - self.window.winfo_width() // 2}+{y}")

    def _hide(self, _event=None) -> None:
        if self.job is not None:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


class FlatVerticalScrollbar(tk.Canvas):
    def __init__(self, parent: tk.Misc, command) -> None:
        super().__init__(
            parent,
            width=12,
            bg="#fafbfc",
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            cursor="arrow",
        )
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self._thumb_top = 0
        self._thumb_bottom = 0
        self._drag_offset: int | None = None
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._mousewheel)

    def set(self, first: str | float, last: str | float) -> None:
        self.first = max(0.0, min(float(first), 1.0))
        self.last = max(self.first, min(float(last), 1.0))
        self._redraw()

    def _geometry(self) -> tuple[int, int, int, float]:
        margin = 4
        track_height = max(self.winfo_height() - margin * 2, 1)
        visible = max(self.last - self.first, 0.0)
        thumb_height = min(track_height, max(28, round(track_height * visible)))
        travel = max(track_height - thumb_height, 0)
        scroll_range = max(1.0 - visible, 0.0)
        position = self.first / scroll_range if scroll_range > 0 else 0.0
        top = margin + round(travel * position)
        return top, top + thumb_height, travel, scroll_range

    def _redraw(self, active: bool = False) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        self.create_line(0, 0, 0, height, fill="#e5e8eb")
        if self.first <= 0.0 and self.last >= 1.0:
            self._thumb_top = self._thumb_bottom = 0
            return
        top, bottom, _travel, _scroll_range = self._geometry()
        self._thumb_top, self._thumb_bottom = top, bottom
        color = "#b8bdc2" if active else "#cdd1d5"
        left, right = 4, max(width - 3, 6)
        radius = max((right - left) // 2, 1)
        self.create_rectangle(left, top + radius, right, bottom - radius, fill=color, outline="")
        self.create_oval(left, top, right, top + radius * 2, fill=color, outline="")
        self.create_oval(left, bottom - radius * 2, right, bottom, fill=color, outline="")

    def _press(self, event) -> None:
        if self._thumb_top <= event.y <= self._thumb_bottom:
            self._drag_offset = event.y - self._thumb_top
            self._redraw(active=True)
            return
        self.command("scroll", -1 if event.y < self._thumb_top else 1, "pages")

    def _drag(self, event) -> None:
        if self._drag_offset is None:
            return
        _top, _bottom, travel, scroll_range = self._geometry()
        if travel <= 0 or scroll_range <= 0:
            return
        target_top = max(4, min(event.y - self._drag_offset, 4 + travel))
        fraction = ((target_top - 4) / travel) * scroll_range
        self.command("moveto", fraction)
        self._redraw(active=True)

    def _release(self, _event=None) -> None:
        self._drag_offset = None
        self._redraw()

    def _mousewheel(self, event) -> str:
        self.command("scroll", -1 if event.delta > 0 else 1, "units")
        return "break"


@dataclass
class CodexConfig:
    config_dir: Path
    api_key: str = ""
    provider: str = DEFAULT_PROVIDER
    base_url: str = DEFAULT_BASE_URL
    model: str = TEMPLATE_MODEL
    model_display_name: str = ""
    auth_exists: bool = False
    config_exists: bool = False


@dataclass(frozen=True)
class BackupSignature:
    auth_exists: bool
    config_exists: bool
    provider_id: str | None
    provider_name: str | None
    base_url: str | None
    model: str | None
    api_key: str | None


@dataclass(frozen=True)
class BackupRecord:
    path: Path
    name: str
    created_at: datetime


@dataclass(frozen=True)
class BackupResult:
    status: str
    record: BackupRecord | None = None


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    parent_pid: int
    executable: Path


@dataclass(frozen=True)
class CodexRestartTarget:
    root_pid: int
    executable: Path
    app_user_model_id: str | None = None


@dataclass(frozen=True)
class ProfileCacheEntry:
    signature: BackupSignature | None
    base_url: str


_PROFILE_CACHE = OrderedDict()
_PROFILE_CACHE_LOCK = threading.Lock()


class ConfigConflictError(OSError):
    pass


class BackupNameError(ValueError):
    pass


class BackupNameConflictError(BackupNameError):
    pass


class ModelListError(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def model_list_endpoint(base_url: str) -> str:
    base_url = base_url.strip()
    if any(character in base_url for character in "\r\n\t"):
        raise ModelListError("Base URL 包含无效字符。")
    try:
        parsed = urllib.parse.urlsplit(base_url)
        hostname = parsed.hostname
    except ValueError as exc:
        raise ModelListError("Base URL 格式无效。") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise ModelListError("Base URL 需要是有效的 http:// 或 https:// 地址。")
    if parsed.username is not None or parsed.password is not None:
        raise ModelListError("Base URL 不能包含用户名或密码。")

    path = parsed.path.rstrip("/")
    if not path.lower().endswith("/models"):
        path += "/models"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def redact_sensitive_text(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Remove known secret values before displaying or recording an error."""
    redacted = str(text)
    for secret in secrets:
        secret = str(secret or "").strip()
        if secret:
            redacted = redacted.replace(secret, "***")
    return redacted


def validate_config_security(config_text: str) -> list[str]:
    """Validate TOML syntax and permission-related key combinations without rewriting them."""
    issues: list[str] = []
    if tomllib is not None:
        try:
            parsed = tomllib.loads(config_text)
        except tomllib.TOMLDecodeError as exc:
            return [f"config.toml 语法无效：{exc}"]
        if not isinstance(parsed, dict):
            return ["config.toml 顶层结构无效。"]
        permission_keys = {key for key in ("default_permissions", "sandbox_mode") if key in parsed}
        if len(permission_keys) == 2:
            issues.append("config.toml 同时设置了 default_permissions 和 sandbox_mode，请只保留一种权限配置。")
        if parsed.get("sandbox_mode") == "danger-full-access":
            issues.append("config.toml 启用了 danger-full-access，软件不会自动扩大此权限。")
        projects = parsed.get("projects")
        if isinstance(projects, dict):
            normalized_projects: dict[str, str] = {}
            for project_path in projects:
                if not isinstance(project_path, str):
                    continue
                normalized = normalized_path_key(Path(project_path))
                previous = normalized_projects.get(normalized)
                if previous is not None and previous != project_path:
                    issues.append(
                        f"config.toml 中的项目路径 {previous!r} 和 {project_path!r} 指向同一位置，请保留一条信任记录。"
                    )
                else:
                    normalized_projects[normalized] = project_path
    return issues


def parse_model_list(payload: bytes) -> list[str]:
    try:
        data = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelListError("模型接口没有返回有效的 JSON。") from exc
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ModelListError("模型接口响应缺少 data 列表。")

    models = set()
    for item in data["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        model_id = item["id"].strip()
        if not model_id or len(model_id) > MODEL_ID_MAX_LENGTH or re.search(r"[\x00-\x1f\x7f]", model_id):
            continue
        models.add(model_id)
        if len(models) >= MODEL_LIST_MAX_ITEMS:
            break
    if not models:
        raise ModelListError("模型接口没有返回可用的模型。")
    return sorted(models, key=str.casefold)


def validate_model_display_name(display_name: str) -> str:
    display_name = display_name.strip()
    if len(display_name) > MODEL_DISPLAY_NAME_MAX_LENGTH:
        raise ConfigConflictError(f"模型显示名称不能超过 {MODEL_DISPLAY_NAME_MAX_LENGTH} 个字符。")
    if re.search(r"[\x00-\x1f\x7f]", display_name):
        raise ConfigConflictError("模型显示名称不能包含控制字符。")
    return display_name


def model_catalog_reference(lines: list[str]) -> tuple[str, str | None]:
    count = count_top_level_key(lines, "model_catalog_json")
    if count > 1:
        raise ConfigConflictError("config.toml 顶层存在多个 model_catalog_json，无法安全修改。")
    reference = get_top_level_value(lines, "model_catalog_json") if count else None
    if reference is None:
        return "none", None
    if reference == MODEL_CATALOG_FILENAME:
        return "owned", reference
    return "external", reference


def is_codex_native_provider(lines: list[str]) -> bool:
    """Whether this config uses Codex's native OpenAI provider metadata."""
    provider_id = (get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER).strip()
    return provider_id == DEFAULT_PROVIDER


def model_catalog_context_window(lines: list[str]) -> int:
    raw_value = get_top_level_value(lines, "model_context_window")
    try:
        value = int(raw_value) if raw_value is not None else 128_000
    except ValueError:
        value = 128_000
    return value if 1_024 <= value <= 10_000_000 else 128_000


def model_catalog_reasoning_effort(lines: list[str]) -> str:
    effort = (get_top_level_value(lines, "model_reasoning_effort") or "high").strip().lower()
    return effort if effort in {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"} else "high"


def model_catalog_reasoning_metadata(config_lines: list[str]) -> tuple[str, list[dict[str, str]]]:
    configured_effort = model_catalog_reasoning_effort(config_lines)
    supported_efforts = {effort for effort, _description in MODEL_CATALOG_REASONING_LEVELS}
    default_effort = configured_effort if configured_effort in supported_efforts else "medium"
    reasoning_levels = [
        {"effort": effort, "description": description}
        for effort, description in MODEL_CATALOG_REASONING_LEVELS
    ]
    return default_effort, reasoning_levels


def read_codex_native_model_entries(config_dir: Path) -> dict[str, dict]:
    """Read Codex's model cache without changing or requiring it."""
    cache_path = config_dir / CODEX_NATIVE_MODEL_CACHE_FILENAME
    try:
        payload = json.loads(read_text(cache_path))
    except (OSError, json.JSONDecodeError):
        return {}
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return {}
    native_models: dict[str, dict] = {}
    for entry in models:
        slug = entry.get("slug") if isinstance(entry, dict) else None
        if isinstance(slug, str) and slug.strip() and slug not in native_models:
            native_models[slug] = copy.deepcopy(entry)
    return native_models


def normalize_owned_model_catalog_reasoning(
    catalog: dict,
    config_lines: list[str],
    native_models: dict[str, dict] | None = None,
) -> dict:
    """Refresh native entries and upgrade only generated entries in memory."""
    default_effort, reasoning_levels = model_catalog_reasoning_metadata(config_lines)
    normalized_models = []
    for original in catalog.get("models", []):
        slug = original.get("slug") if isinstance(original, dict) else None
        if isinstance(slug, str) and native_models is not None and slug in native_models:
            normalized_models.append(copy.deepcopy(native_models[slug]))
            continue
        entry = dict(original)
        entry["default_reasoning_level"] = default_effort
        entry["supported_reasoning_levels"] = [dict(level) for level in reasoning_levels]
        normalized_models.append(entry)
    normalized = dict(catalog)
    normalized["models"] = normalized_models
    return normalized


def build_model_catalog(
    model: str,
    display_name: str,
    config_lines: list[str],
    native_models: dict[str, dict] | None = None,
) -> dict:
    model = model.strip()
    if not model:
        raise ConfigConflictError("Model 不能为空。")
    if native_models is not None and model in native_models:
        return {"models": [copy.deepcopy(native_models[model])]}
    display_name = validate_model_display_name(display_name)
    context_window = model_catalog_context_window(config_lines)
    default_effort, reasoning_levels = model_catalog_reasoning_metadata(config_lines)
    return {
        "models": [
            {
                "slug": model,
                "display_name": display_name,
                "description": display_name,
                "base_instructions": (
                    "You are Codex, a coding agent. You and the user share the same workspace "
                    "and collaborate to achieve the user's goals."
                ),
                "default_reasoning_level": default_effort,
                "supported_reasoning_levels": reasoning_levels,
                "shell_type": "shell_command",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 1000,
                "supports_reasoning_summaries": True,
                "default_reasoning_summary": "none",
                "support_verbosity": False,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "supports_parallel_tool_calls": False,
                "supports_image_detail_original": False,
                "context_window": context_window,
                "max_context_window": context_window,
                "effective_context_window_percent": 95,
                "experimental_supported_tools": [],
                "input_modalities": ["text", "image"],
                "supports_search_tool": False,
            }
        ]
    }


def automatic_model_display_name(model: str) -> str:
    """Create a readable Codex label while preserving the real model slug."""
    parts = re.split(r"[-_]+", model.strip())
    return " ".join(part.upper() if re.fullmatch(r"v?\d+(?:\.\d+)*", part, re.IGNORECASE) else part.title() for part in parts if part)


def remove_owned_model_catalog_projection(config_dir: Path, lines: list[str]) -> None:
    """Remove only the catalog owned by this application, preserving external catalogs."""
    status, _reference = model_catalog_reference(lines)
    if status == "external":
        return
    config_path = config_dir / "config.toml"
    if status == "owned":
        write_text(config_path, "".join(remove_top_level_key(lines, "model_catalog_json")))
    catalog_path = config_dir / MODEL_CATALOG_FILENAME
    if catalog_path.exists():
        catalog_path.unlink()


def update_owned_model_catalog_models(
    config_dir: Path,
    models: list[str],
    native_catalog_dir: Path | None = None,
) -> None:
    config_path = config_dir / "config.toml"
    if not config_path.exists():
        raise ConfigConflictError("current config.toml is missing")
    lines = read_text(config_path).splitlines(keepends=True)
    status, reference = model_catalog_reference(lines)
    provider_id = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
    if is_codex_native_provider(lines):
        remove_owned_model_catalog_projection(config_dir, lines)
        return
    if status == "external":
        raise ConfigConflictError(f"当前配置已使用用户模型目录 {reference!r}，配置助手不会覆盖")
    normalized = []
    seen = set()
    for model in models:
        model = model.strip()
        if model and model not in seen:
            seen.add(model)
            normalized.append(model)
    if not normalized:
        raise ConfigConflictError("模型列表为空")
    current_model = (get_top_level_value(lines, "model") or "").strip()
    if current_model and current_model not in seen:
        normalized.insert(0, current_model)
    native_models = read_codex_native_model_entries(native_catalog_dir or config_dir)
    entries = []
    for model in normalized:
        entry = build_model_catalog(
            model,
            automatic_model_display_name(model),
            lines,
            native_models,
        )["models"][0]
        entries.append(entry)
    catalog_path = config_dir / MODEL_CATALOG_FILENAME
    write_text(catalog_path, json.dumps({"models": entries}, ensure_ascii=False, indent=2) + "\n")
    write_text(config_path, "".join(replace_or_insert_top_level(lines, "model_catalog_json", MODEL_CATALOG_FILENAME)))


def read_model_display_name(config_dir: Path, model: str | None = None) -> str:
    config_path = config_dir / "config.toml"
    catalog_path = config_dir / MODEL_CATALOG_FILENAME
    if not config_path.exists() or not catalog_path.exists():
        return ""
    lines = read_text(config_path).splitlines(keepends=True)
    status, _reference = model_catalog_reference(lines)
    if status != "owned":
        return ""
    target_model = (model or get_top_level_value(lines, "model") or "").strip()
    try:
        catalog = json.loads(read_text(catalog_path))
    except json.JSONDecodeError:
        return ""
    models = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(models, list):
        return ""
    for entry in models:
        if not isinstance(entry, dict) or entry.get("slug") != target_model:
            continue
        display_name = entry.get("display_name")
        if isinstance(display_name, str):
            try:
                return validate_model_display_name(display_name)
            except ConfigConflictError:
                return ""
    return ""


def read_owned_model_catalog_models(config_dir: Path) -> list[str]:
    """Read model slugs from the configuration assistant's owned catalog."""
    config_path = config_dir / "config.toml"
    catalog_path = config_dir / MODEL_CATALOG_FILENAME
    if not config_path.exists() or not catalog_path.exists():
        return []
    try:
        lines = read_text(config_path).splitlines(keepends=True)
        status, _reference = model_catalog_reference(lines)
        if status != "owned":
            return []
        catalog = json.loads(read_text(catalog_path))
    except (OSError, json.JSONDecodeError):
        return []
    entries = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(entries, list):
        return []
    models: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        slug = entry.get("slug") if isinstance(entry, dict) else entry
        if isinstance(slug, str) and slug.strip() and slug.strip() not in seen:
            slug = slug.strip()
            seen.add(slug)
            models.append(slug)
    return models


def read_owned_model_catalog(config_dir: Path) -> dict:
    """Read and validate the complete catalog owned by this application."""
    config_path = config_dir / "config.toml"
    catalog_path = config_dir / MODEL_CATALOG_FILENAME
    if not config_path.exists():
        raise ConfigConflictError("当前配置缺少 config.toml。")
    lines = read_text(config_path).splitlines(keepends=True)
    status, _reference = model_catalog_reference(lines)
    if status != "owned" or not catalog_path.exists():
        raise ConfigConflictError("配置助手模型目录缺失。")
    try:
        catalog = json.loads(read_text(catalog_path))
    except json.JSONDecodeError as exc:
        raise ConfigConflictError("配置助手模型目录不是有效 JSON。") from exc
    entries = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ConfigConflictError("配置助手模型目录缺少 models 列表。")
    seen: set[str] = set()
    for entry in entries:
        slug = entry.get("slug") if isinstance(entry, dict) else None
        if not isinstance(slug, str) or not slug.strip() or slug.strip() in seen:
            raise ConfigConflictError("配置助手模型目录包含无效或重复的模型标识。")
        seen.add(slug.strip())
    return catalog


def ensure_model_in_owned_catalog(
    config_dir: Path,
    model: str,
    native_catalog_dir: Path | None = None,
) -> None:
    """Keep a complete owned catalog intact and append a manually entered model if needed."""
    config_path = config_dir / "config.toml"
    if not config_path.exists():
        raise ConfigConflictError("当前配置缺少 config.toml。")
    lines = read_text(config_path).splitlines(keepends=True)
    status, _reference = model_catalog_reference(lines)
    provider_id = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
    if is_codex_native_provider(lines):
        remove_owned_model_catalog_projection(config_dir, lines)
        return
    if status != "owned":
        return
    catalog = read_owned_model_catalog(config_dir)
    model = model.strip()
    entries = catalog["models"]
    native_models = read_codex_native_model_entries(native_catalog_dir or config_dir)
    matching_index = next(
        (
            index
            for index, entry in enumerate(entries)
            if isinstance(entry, dict) and entry.get("slug") == model
        ),
        None,
    )
    if matching_index is not None and model in native_models:
        native_entry = copy.deepcopy(native_models[model])
        if entries[matching_index] != native_entry:
            entries[matching_index] = native_entry
            write_text(
                config_dir / MODEL_CATALOG_FILENAME,
                json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            )
        return
    if matching_index is not None:
        return
    entries.append(
        build_model_catalog(
            model,
            automatic_model_display_name(model),
            lines,
            native_models,
        )["models"][0]
    )
    write_text(
        config_dir / MODEL_CATALOG_FILENAME,
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
    )


def save_available_models(
    config_dir: Path,
    models: list[str],
    profile_dir: Path | None = None,
) -> BackupRecord | None:
    """Persist one provider's complete model list to live and saved configuration atomically."""
    active = resolve_active_profile(config_dir) if profile_dir is None else backup_record_from_path(profile_dir)
    current_snapshot = capture_config_files(config_dir)
    profile_snapshot = capture_config_files(active.path) if active is not None else None
    try:
        update_owned_model_catalog_models(config_dir, models, native_catalog_dir=config_dir)
        if active is not None:
            update_owned_model_catalog_models(active.path, models, native_catalog_dir=config_dir)
    except (OSError, ConfigConflictError):
        restore_config_files(config_dir, current_snapshot)
        if active is not None and profile_snapshot is not None:
            restore_config_files(active.path, profile_snapshot)
        raise
    finally:
        clear_profile_cache()
    return active


def update_owned_model_catalog(
    config_dir: Path,
    display_name: str,
    native_catalog_dir: Path | None = None,
) -> None:
    config_path = config_dir / "config.toml"
    if not config_path.exists():
        raise ConfigConflictError("当前配置缺少 config.toml。")
    display_name = validate_model_display_name(display_name)
    lines = read_text(config_path).splitlines(keepends=True)
    status, reference = model_catalog_reference(lines)
    provider_id = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
    if provider_id == DEFAULT_PROVIDER:
        remove_owned_model_catalog_projection(config_dir, lines)
        return
    catalog_path = config_dir / MODEL_CATALOG_FILENAME

    if display_name:
        if status == "external":
            raise ConfigConflictError(
                f"当前配置已使用用户模型目录 {reference!r}，配置助手不会覆盖。"
            )
        model = (get_top_level_value(lines, "model") or "").strip()
        native_models = read_codex_native_model_entries(native_catalog_dir or config_dir)
        catalog = build_model_catalog(model, display_name, lines, native_models)
        write_text(catalog_path, json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
        lines = replace_or_insert_top_level(lines, "model_catalog_json", MODEL_CATALOG_FILENAME)
        write_text(config_path, "".join(lines))
        return

    if status == "owned":
        write_text(config_path, "".join(remove_top_level_key(lines, "model_catalog_json")))
    if status != "external" and catalog_path.exists():
        catalog_path.unlink()


def save_active_model_display_name(config_dir: Path, display_name: str) -> BackupRecord | None:
    """Update only the active model display name and its matching saved profile."""
    display_name = validate_model_display_name(display_name)
    active_profile = find_matching_backup(config_dir)
    current_snapshot = capture_config_files(config_dir)
    profile_snapshot = capture_config_files(active_profile.path) if active_profile is not None else None
    try:
        if active_profile is not None:
            update_owned_model_catalog(active_profile.path, display_name, native_catalog_dir=config_dir)
        update_owned_model_catalog(config_dir, display_name, native_catalog_dir=config_dir)
    except (OSError, ConfigConflictError):
        restore_config_files(config_dir, current_snapshot)
        if active_profile is not None and profile_snapshot is not None:
            restore_config_files(active_profile.path, profile_snapshot)
        raise
    finally:
        clear_profile_cache()
    return active_profile


def fetch_available_models(
    base_url: str,
    api_key: str,
    timeout: float = MODEL_LIST_TIMEOUT_SECONDS,
) -> list[str]:
    endpoint = model_list_endpoint(base_url)
    api_key = api_key.strip()
    if "\r" in api_key or "\n" in api_key:
        raise ModelListError("API Key 包含无效字符。")
    headers = {
        "Accept": "application/json",
        "User-Agent": f"CodexConfigTool/{APP_VERSION}",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        request = urllib.request.Request(endpoint, headers=headers, method="GET")
    except (ValueError, UnicodeError) as exc:
        raise ModelListError("模型接口地址无效。") from exc
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(MODEL_LIST_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ModelListError(f"模型接口返回 HTTP {exc.code}。") from exc
    except urllib.error.URLError as exc:
        reason = str(exc.reason).strip() or "连接失败"
        raise ModelListError(f"无法连接模型接口：{redact_sensitive_text(reason, (api_key,))}") from exc
    except TimeoutError as exc:
        raise ModelListError("连接模型接口超时。") from exc
    except OSError as exc:
        raise ModelListError(f"无法连接模型接口：{redact_sensitive_text(str(exc), (api_key,))}") from exc
    except (ValueError, UnicodeError) as exc:
        raise ModelListError("模型接口地址无效。") from exc

    if len(payload) > MODEL_LIST_MAX_BYTES:
        raise ModelListError("模型接口响应过大，已停止读取。")
    return parse_model_list(payload)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_copy_file(source: Path, target: Path) -> None:
    atomic_write_bytes(target, source.read_bytes())


def is_codex_config_dir(path: Path) -> bool:
    return path.is_dir() and ((path / "auth.json").exists() or (path / "config.toml").exists())


def candidate_config_dirs() -> list[Path]:
    home = Path.home()
    env_home = os.environ.get("CODEX_HOME")
    candidates = []
    if env_home:
        candidates.append(Path(env_home))
    candidates.extend(
        [
            home / ".codex",
            Path(os.environ.get("APPDATA", "")) / "Codex",
            Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex",
            Path.cwd() / ".codex",
        ]
    )
    seen = set()
    unique = []
    for item in candidates:
        try:
            resolved = item.expanduser().resolve()
        except OSError:
            resolved = item.expanduser()
        if str(resolved).lower() not in seen:
            seen.add(str(resolved).lower())
            unique.append(resolved)
    return unique


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(config_dir: Path) -> None:
    settings = load_settings()
    settings["config_dir"] = str(canonical_config_path(config_dir))
    write_text(SETTINGS_FILE, json.dumps(settings, ensure_ascii=False, indent=2))


def save_setting_value(key: str, value: object) -> None:
    settings = load_settings()
    settings[key] = value
    write_text(SETTINGS_FILE, json.dumps(settings, ensure_ascii=False, indent=2))


ACTIVE_PROFILE_PATH_KEY = "active_profile_path"
PENDING_ACTIVE_PROFILE_PATH_KEY = "pending_active_profile_path"


def active_profile_path(config_dir: Path) -> Path | None:
    value = load_settings().get(ACTIVE_PROFILE_PATH_KEY)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return validate_backup_path(config_dir, Path(value))
    except OSError:
        return None


def set_active_profile_path(profile_dir: Path | None) -> None:
    save_setting_value(ACTIVE_PROFILE_PATH_KEY, str(profile_dir.resolve()) if profile_dir is not None else "")


def pending_active_profile_path(config_dir: Path) -> Path | None:
    value = load_settings().get(PENDING_ACTIVE_PROFILE_PATH_KEY)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        profile_dir = validate_backup_path(config_dir, Path(value))
    except OSError:
        return None
    return profile_dir if profile_dir.is_dir() else None


def set_pending_active_profile_path(profile_dir: Path | None) -> None:
    save_setting_value(
        PENDING_ACTIVE_PROFILE_PATH_KEY,
        str(profile_dir.resolve()) if profile_dir is not None else "",
    )


def profile_has_pending_apply(config_dir: Path, profile_dir: Path) -> bool:
    pending = pending_active_profile_path(config_dir)
    return pending is not None and normalized_path_key(pending) == normalized_path_key(profile_dir)


def same_profile_identity(left: BackupSignature | None, right: BackupSignature | None) -> bool:
    """Compare provider identity while allowing Codex to change model state."""
    if left is None or right is None:
        return False
    return (
        left.auth_exists == right.auth_exists
        and left.config_exists == right.config_exists
        and left.provider_id == right.provider_id
        and left.provider_name == right.provider_name
        and left.base_url == right.base_url
        and left.api_key == right.api_key
    )


def resolve_active_profile(config_dir: Path) -> BackupRecord | None:
    """Resolve the active profile without writing live state to a different provider."""
    current_signature = build_backup_signature(config_dir)
    configured = active_profile_path(config_dir)
    if configured is not None and configured.is_dir():
        if same_profile_identity(current_signature, build_backup_signature(configured)):
            return backup_record_from_path(configured)
    for record in list_backup_records(config_dir):
        if same_profile_identity(current_signature, build_backup_signature(record.path)):
            return record
    return None


def sync_current_to_active_profile(config_dir: Path) -> BackupRecord | None:
    """Sync public launch defaults and tool-owned catalogs to the matching profile."""
    active = resolve_active_profile(config_dir)
    if active is None:
        return None
    profile_dir = active.path
    profile_snapshot = capture_config_files(profile_dir)
    try:
        for file_name in ("auth.json", "config.toml"):
            source = config_dir / file_name
            target = profile_dir / file_name
            if source.exists():
                atomic_copy_file(source, target)
            elif target.exists():
                target.unlink()
        live_config = config_dir / "config.toml"
        live_lines = read_text(live_config).splitlines(keepends=True) if live_config.exists() else []
        catalog_status, _reference = model_catalog_reference(live_lines)
        source_catalog = config_dir / MODEL_CATALOG_FILENAME
        target_catalog = profile_dir / MODEL_CATALOG_FILENAME
        if catalog_status == "owned":
            read_owned_model_catalog(config_dir)
            atomic_copy_file(source_catalog, target_catalog)
        elif target_catalog.exists():
            target_catalog.unlink()
        clear_profile_cache()
        set_active_profile_path(profile_dir)
        return backup_record_from_path(profile_dir)
    except (OSError, ConfigConflictError):
        restore_config_files(profile_dir, profile_snapshot)
        raise


def should_show_onboarding(settings: dict) -> bool:
    return not bool(settings.get(HIDE_ONBOARDING_KEY, False))


def normalized_path_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve()).lower()
    except OSError:
        return str(path.expanduser()).lower()


def canonical_config_path(path: Path) -> Path:
    """Use one absolute, normalized path for settings and project identity."""
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def is_official_login_mode(config_dir: Path) -> bool:
    return load_settings().get(OFFICIAL_LOGIN_MODE_PATH_KEY) == normalized_path_key(config_dir)


def set_official_login_mode(config_dir: Path, enabled: bool) -> None:
    save_setting_value(OFFICIAL_LOGIN_MODE_PATH_KEY, normalized_path_key(config_dir) if enabled else "")

def quote_toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def format_toml_value(value: str | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return quote_toml_string(value)


def unquote_toml_string(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, str) else value[1:-1]
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def split_toml_value_and_comment(line: str) -> tuple[str, str]:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_double:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return line[:index].rstrip(), line[index:].rstrip("\n")
    return line.rstrip("\n"), ""


def section_name_from_line(line: str) -> str | None:
    match = re.match(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$", line)
    return match.group(1).strip() if match else None


def count_top_level_key(lines: list[str], key: str) -> int:
    current_section = None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    count = 0
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
            continue
        if current_section is None and pattern.match(line):
            count += 1
    return count


def count_sections(lines: list[str], section_name: str) -> int:
    return sum(1 for line in lines if section_name_from_line(line) == section_name)


def count_section_key(lines: list[str], section_name: str, key: str) -> int:
    current_section = None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    count = 0
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
            continue
        if current_section == section_name and pattern.match(line):
            count += 1
    return count


def get_top_level_value(lines: list[str], key: str) -> str | None:
    current_section = None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+)$")
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
            continue
        if current_section is None:
            match = pattern.match(line)
            if match:
                raw, _comment = split_toml_value_and_comment(match.group(1))
                return unquote_toml_string(raw.strip())
    return None


def get_section_value(lines: list[str], section_name: str, key: str) -> str | None:
    current_section = None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+)$")
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
            continue
        if current_section == section_name:
            match = pattern.match(line)
            if match:
                raw, _comment = split_toml_value_and_comment(match.group(1))
                return unquote_toml_string(raw.strip())
    return None


def replace_or_insert_top_level(lines: list[str], key: str, value: str) -> list[str]:
    output = []
    current_section = None
    replaced = False
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=\s*(.*)$")
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            if not replaced and current_section is None:
                output.append(f"{key} = {quote_toml_string(value)}\n")
                replaced = True
            current_section = section
        if current_section is None:
            match = pattern.match(line)
            if match:
                raw, comment = split_toml_value_and_comment(match.group(2))
                suffix = f" {comment}" if comment else ""
                output.append(f"{match.group(1)}{key} = {quote_toml_string(value)}{suffix}\n")
                replaced = True
                continue
        output.append(line)
    if not replaced:
        output.insert(0, f"{key} = {quote_toml_string(value)}\n")
    return output


def replace_existing_top_level(lines: list[str], key: str, value: str) -> list[str]:
    output = []
    current_section = None
    replaced = False
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=\s*(.*)$")
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
        if current_section is None:
            match = pattern.match(line)
            if match:
                _raw, comment = split_toml_value_and_comment(match.group(2))
                suffix = f" {comment}" if comment else ""
                output.append(f"{match.group(1)}{key} = {quote_toml_string(value)}{suffix}\n")
                replaced = True
                continue
        output.append(line)
    if not replaced:
        raise ConfigConflictError(f"没有找到可修改的顶层 {key}")
    return output


def remove_top_level_key(lines: list[str], key: str) -> list[str]:
    """Remove one managed top-level key while preserving comments and sections."""
    output = []
    current_section = None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
        if current_section is None and pattern.match(line):
            continue
        output.append(line)
    return output


def remove_top_level_key(lines: list[str], key: str) -> list[str]:
    output = []
    current_section = None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
        if current_section is None and pattern.match(line):
            continue
        output.append(line)
    return output


def remove_section(lines: list[str], section_name: str) -> list[str]:
    output = []
    in_target = False
    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            in_target = section == section_name
            if in_target:
                continue
        if not in_target:
            output.append(line)
    return output


def replace_section_header(lines: list[str], old_section_name: str, new_section_name: str) -> list[str]:
    output = []
    replaced = False
    for line in lines:
        section = section_name_from_line(line)
        if section == old_section_name:
            output.append(f"[{new_section_name}]\n")
            replaced = True
            continue
        output.append(line)
    if not replaced:
        raise ConfigConflictError(f"没有找到可修改的 [{old_section_name}] 段")
    return output


def replace_existing_section_value(lines: list[str], section_name: str, key: str, value: str | bool) -> list[str]:
    output = []
    current_section = None
    replaced = False
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=\s*(.*)$")

    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            current_section = section
        if current_section == section_name:
            match = pattern.match(line)
            if match:
                _raw, comment = split_toml_value_and_comment(match.group(2))
                suffix = f" {comment}" if comment else ""
                output.append(f"{match.group(1)}{key} = {format_toml_value(value)}{suffix}\n")
                replaced = True
                continue
        output.append(line)

    if not replaced:
        raise ConfigConflictError(f"没有找到可修改的 [{section_name}] 段中的 {key}")
    return output


def append_provider_section(
    lines: list[str],
    provider: str,
    base_url: str,
    display_name: str | None = None,
) -> list[str]:
    output = list(lines)
    display_name = display_name.strip() if display_name is not None else provider
    if output and not output[-1].endswith("\n"):
        output[-1] += "\n"
    if output and output[-1].strip():
        output.append("\n")
    output.extend(
        [
            f"[model_providers.{provider}]\n",
            f"name = {quote_toml_string(display_name)}\n",
            f"base_url = {quote_toml_string(base_url)}\n",
            'wire_api = "responses"\n',
            "requires_openai_auth = true\n",
        ]
    )
    return output


def replace_or_insert_section_value(lines: list[str], section_name: str, key: str, value: str | bool) -> list[str]:
    output = []
    current_section = None
    in_target = False
    section_found = False
    key_replaced = False
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=\s*(.*)$")

    for line in lines:
        section = section_name_from_line(line)
        if section is not None:
            if in_target and not key_replaced:
                output.append(f"{key} = {format_toml_value(value)}\n")
                key_replaced = True
            current_section = section
            in_target = current_section == section_name
            section_found = section_found or in_target

        if in_target:
            match = pattern.match(line)
            if match:
                raw, comment = split_toml_value_and_comment(match.group(2))
                suffix = f" {comment}" if comment else ""
                output.append(f"{match.group(1)}{key} = {format_toml_value(value)}{suffix}\n")
                key_replaced = True
                continue
        output.append(line)

    if section_found and in_target and not key_replaced:
        output.append(f"{key} = {format_toml_value(value)}\n")
        key_replaced = True

    if not section_found:
        if output and not output[-1].endswith("\n"):
            output[-1] += "\n"
        if output and output[-1].strip():
            output.append("\n")
        output.extend(
            [
                f"[{section_name}]\n",
                f"name = {quote_toml_string(section_name.split('.', 1)[1])}\n",
                f"base_url = {quote_toml_string(value)}\n",
                'wire_api = "responses"\n',
                "requires_openai_auth = true\n",
            ]
        )
    return output


def read_codex_config(config_dir: Path) -> CodexConfig:
    auth_path = config_dir / "auth.json"
    config_path = config_dir / "config.toml"
    result = CodexConfig(config_dir=config_dir, auth_exists=auth_path.exists(), config_exists=config_path.exists())

    if auth_path.exists():
        try:
            auth_data = json.loads(read_text(auth_path))
            if isinstance(auth_data, dict):
                result.api_key = str(auth_data.get("OPENAI_API_KEY", ""))
        except json.JSONDecodeError:
            result.api_key = ""

    if config_path.exists():
        lines = read_text(config_path).splitlines(keepends=True)
        provider = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
        provider_section = f"model_providers.{provider}"
        result.provider = get_section_value(lines, provider_section, "name") or provider
        result.base_url = get_section_value(lines, provider_section, "base_url") or DEFAULT_BASE_URL
        result.model = get_top_level_value(lines, "model") or TEMPLATE_MODEL
        result.model_display_name = read_model_display_name(config_dir, result.model)

    return result


def validate_backup_name_format(name: str) -> str:
    name = name.strip()
    if not name:
        raise BackupNameError("配置名称不能为空。")
    if len(name) > MAX_BACKUP_NAME_LENGTH:
        raise BackupNameError(f"配置名称不能超过 {MAX_BACKUP_NAME_LENGTH} 个字符。")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise BackupNameError('配置名称不能包含 < > : " / \\ | ? * 等字符。')
    if name in {".", ".."} or name.endswith("."):
        raise BackupNameError("配置名称不能是点号，也不能以点号结尾。")
    return name


def suggested_config_name(provider_name: str) -> str:
    suggestion = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", provider_name).strip(". ")
    return suggestion[:MAX_BACKUP_NAME_LENGTH] or "backup"


def suggested_backup_name(config_dir: Path) -> str:
    provider_name = read_codex_config(config_dir).provider.strip() or DEFAULT_PROVIDER
    return suggested_config_name(provider_name)


def backup_record_from_path(path: Path) -> BackupRecord:
    match = BACKUP_DIR_PATTERN.match(path.name)
    if match:
        try:
            created_at = datetime.strptime(match.group("timestamp"), BACKUP_TIMESTAMP_FORMAT)
        except ValueError:
            created_at = datetime.fromtimestamp(path.stat().st_mtime)
        name = match.group("name")
    else:
        created_at = datetime.fromtimestamp(path.stat().st_mtime)
        name = path.name
    return BackupRecord(path=path, name=name, created_at=created_at)


def list_backup_records(config_dir: Path) -> list[BackupRecord]:
    backup_root = config_dir / "backups"
    if not backup_root.exists():
        return []
    records = []
    for item in backup_root.iterdir():
        if item.is_dir() and ((item / "auth.json").exists() or (item / "config.toml").exists()):
            records.append(backup_record_from_path(item))
    return sorted(records, key=lambda item: item.created_at, reverse=True)


def list_backups(config_dir: Path) -> list[Path]:
    return [record.path for record in list_backup_records(config_dir)]


def _profile_fingerprint(config_dir: Path) -> tuple[tuple[bool, int, int, int], ...]:
    fingerprint = []
    for file_name in ("auth.json", "config.toml"):
        try:
            stat = (config_dir / file_name).stat()
            fingerprint.append((True, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        except OSError:
            fingerprint.append((False, 0, 0, 0))
    return tuple(fingerprint)


def _build_backup_signature_uncached(config_dir: Path) -> BackupSignature | None:
    auth_path = config_dir / "auth.json"
    config_path = config_dir / "config.toml"
    auth_exists = auth_path.exists()
    config_exists = config_path.exists()
    if not auth_exists and not config_exists:
        return None

    api_key = ""
    if auth_exists:
        auth_text = read_text(auth_path)
        if len(re.findall(r'"OPENAI_API_KEY"\s*:', auth_text)) > 1:
            return None
        try:
            auth_data = json.loads(auth_text)
        except json.JSONDecodeError:
            return None
        if not isinstance(auth_data, dict):
            return None
        api_key = str(auth_data.get("OPENAI_API_KEY", ""))

    provider_id = None
    provider_name = None
    base_url = None
    model = None
    if config_exists:
        lines = read_text(config_path).splitlines(keepends=True)
        provider_count = count_top_level_key(lines, "model_provider")
        model_count = count_top_level_key(lines, "model")
        if provider_count > 1 or model_count > 1:
            return None
        provider_id = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
        model = get_top_level_value(lines, "model") or TEMPLATE_MODEL
        provider_section = f"model_providers.{provider_id}"
        section_count = count_sections(lines, provider_section)
        if section_count > 1:
            return None
        if section_count == 0:
            if provider_id != DEFAULT_PROVIDER:
                return None
            provider_name = DEFAULT_PROVIDER
            base_url = DEFAULT_BASE_URL
        else:
            if count_section_key(lines, provider_section, "name") != 1:
                return None
            if count_section_key(lines, provider_section, "base_url") != 1:
                return None
            provider_name = get_section_value(lines, provider_section, "name")
            base_url = get_section_value(lines, provider_section, "base_url")
            if provider_name is None or base_url is None:
                return None

    return BackupSignature(
        auth_exists=auth_exists,
        config_exists=config_exists,
        provider_id=provider_id,
        provider_name=provider_name,
        base_url=base_url,
        model=model,
        api_key=api_key,
    )


def cached_profile_entry(config_dir: Path) -> ProfileCacheEntry:
    cache_key = normalized_path_key(config_dir)
    fingerprint = _profile_fingerprint(config_dir)
    with _PROFILE_CACHE_LOCK:
        cached = _PROFILE_CACHE.get(cache_key)
        if cached is not None and cached[0] == fingerprint:
            _PROFILE_CACHE.move_to_end(cache_key)
            return cached[1]

    signature = _build_backup_signature_uncached(config_dir)
    base_url = signature.base_url if signature is not None and signature.base_url else DEFAULT_BASE_URL
    if signature is None:
        base_url = read_codex_config(config_dir).base_url
    entry = ProfileCacheEntry(signature=signature, base_url=base_url)

    with _PROFILE_CACHE_LOCK:
        _PROFILE_CACHE[cache_key] = (fingerprint, entry)
        _PROFILE_CACHE.move_to_end(cache_key)
        while len(_PROFILE_CACHE) > PROFILE_CACHE_LIMIT:
            _PROFILE_CACHE.popitem(last=False)
    return entry


def build_backup_signature(config_dir: Path) -> BackupSignature | None:
    return cached_profile_entry(config_dir).signature


def clear_profile_cache() -> None:
    with _PROFILE_CACHE_LOCK:
        _PROFILE_CACHE.clear()


def named_backup_records(config_dir: Path, name: str, exclude_path: Path | None = None) -> list[BackupRecord]:
    name_key = name.casefold()
    excluded_key = normalized_path_key(exclude_path) if exclude_path is not None else None
    return [
        record
        for record in list_backup_records(config_dir)
        if record.name.casefold() == name_key and normalized_path_key(record.path) != excluded_key
    ]


def find_matching_backup(
    config_dir: Path,
    signature: BackupSignature | None = None,
    exclude_path: Path | None = None,
) -> BackupRecord | None:
    signature = signature if signature is not None else build_backup_signature(config_dir)
    if signature is None:
        return None
    excluded_key = normalized_path_key(exclude_path) if exclude_path is not None else None
    for record in list_backup_records(config_dir):
        if normalized_path_key(record.path) != excluded_key and build_backup_signature(record.path) == signature:
            return record
    return None


def validate_new_backup_name(config_dir: Path, name: str) -> str:
    name = validate_backup_name_format(name)
    if named_backup_records(config_dir, name):
        raise BackupNameConflictError("已存在同名配置，请使用新的配置名称。")
    return name


def capture_config_files(config_dir: Path) -> dict[str, bytes | None]:
    return {
        file_name: (config_dir / file_name).read_bytes() if (config_dir / file_name).exists() else None
        for file_name in MANAGED_CONFIG_FILE_NAMES
    }


def restore_config_files(config_dir: Path, snapshot: dict[str, bytes | None]) -> None:
    for file_name, content in snapshot.items():
        path = config_dir / file_name
        if content is None:
            if path.exists():
                path.unlink()
        else:
            atomic_write_bytes(path, content)


def copy_config_files(source_dir: Path, target_dir: Path) -> None:
    """Copy the current Codex files before changing only managed fields."""
    target_dir.mkdir(parents=True, exist_ok=True)
    for file_name in MANAGED_CONFIG_FILE_NAMES:
        source = source_dir / file_name
        if source.exists():
            shutil.copy2(source, target_dir / file_name)


def create_named_backup(config_dir: Path, name: str | None) -> BackupRecord:
    has_source = any((config_dir / file_name).exists() for file_name in ("auth.json", "config.toml"))
    if not has_source:
        raise BackupNameError("当前没有可保存的配置。")
    if name is None:
        raise BackupNameError("新增配置必须先填写配置名称。")

    name = validate_new_backup_name(config_dir, name)

    backup_root = config_dir / "backups"
    timestamp = datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
    backup_dir = backup_root / f"{timestamp}-{name}"
    if backup_dir.exists():
        raise BackupNameConflictError("同一秒内已存在同名配置，请稍后重试或使用新的名称。")
    backup_dir.mkdir(parents=True, exist_ok=False)
    try:
        for file_name in MANAGED_CONFIG_FILE_NAMES:
            source = config_dir / file_name
            if source.exists():
                atomic_copy_file(source, backup_dir / file_name)
    except OSError:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    return backup_record_from_path(backup_dir)


def create_config_profile(
    config_dir: Path,
    name: str,
    api_key: str,
    provider_name: str,
    base_url: str,
    model: str,
    apply_to_current: bool = False,
    model_display_name: str = "",
    available_models: list[str] | None = None,
) -> BackupRecord:
    state, issues = classify_config_for_editing(config_dir)
    if state == "conflict":
        raise ConfigConflictError(
            "当前配置包含复杂或冲突内容，无法安全新增配置。\n\n"
            + "\n".join(f"- {item}" for item in issues)
        )
    name = validate_new_backup_name(config_dir, name)
    signature = build_requested_signature(
        config_dir,
        api_key,
        provider_name,
        base_url,
        model,
        state,
    )
    existing = find_matching_backup(config_dir, signature)
    if existing is not None:
        raise BackupNameConflictError(f"已存在相同配置：{existing.name}")

    backup_root = config_dir / "backups"
    timestamp = datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
    profile_dir = backup_root / f"{timestamp}-{name}"
    if profile_dir.exists():
        raise BackupNameConflictError("同一秒内已存在同名配置，请稍后重试或使用新的名称。")

    current_snapshot = capture_config_files(config_dir) if apply_to_current else None
    profile_dir.mkdir(parents=True, exist_ok=False)
    try:
        create_profile_from_current_config(
            config_dir,
            profile_dir,
            api_key,
            provider_name,
            base_url,
            model,
            state,
            model_display_name,
            available_models,
        )
        record = backup_record_from_path(profile_dir)
        if apply_to_current:
            restore_backup(config_dir, record.path)
    except (OSError, json.JSONDecodeError, ConfigConflictError):
        shutil.rmtree(profile_dir, ignore_errors=True)
        if current_snapshot is not None:
            restore_config_files(config_dir, current_snapshot)
        raise
    return record


def update_config_profile(
    config_dir: Path,
    profile_dir: Path,
    name: str,
    api_key: str,
    provider_name: str,
    base_url: str,
    model: str,
    apply_to_current: bool = False,
    model_display_name: str = "",
    available_models: list[str] | None = None,
) -> BackupRecord:
    profile_dir = validate_backup_path(config_dir, profile_dir)
    original_record = backup_record_from_path(profile_dir)
    name = validate_backup_name_format(name)
    if named_backup_records(config_dir, name, exclude_path=profile_dir):
        raise BackupNameConflictError("已存在同名配置，请使用新的配置名称。")

    state, issues = classify_config_for_editing(profile_dir)
    if state == "conflict":
        raise ConfigConflictError(
            "选择的配置包含复杂或冲突内容，无法安全编辑。\n\n"
            + "\n".join(f"- {item}" for item in issues)
        )
    signature = build_requested_signature(
        profile_dir,
        api_key,
        provider_name,
        base_url,
        model,
        state,
    )
    duplicate = find_matching_backup(config_dir, signature, exclude_path=profile_dir)
    if duplicate is not None:
        raise BackupNameConflictError(f"已存在相同配置：{duplicate.name}")

    profile_snapshot = capture_config_files(profile_dir)
    current_snapshot = capture_config_files(config_dir) if apply_to_current else None
    updated_path = profile_dir
    try:
        if state == "needs_template":
            save_custom_provider_config(
                profile_dir,
                api_key,
                provider_name,
                base_url,
                model,
                model_display_name=model_display_name,
                persist_settings=False,
                native_catalog_dir=config_dir,
            )
        else:
            save_codex_config(
                profile_dir,
                api_key,
                provider_name,
                base_url,
                model,
                model_display_name=model_display_name,
                persist_settings=False,
                native_catalog_dir=config_dir,
            )
        profile_lines = read_text(profile_dir / "config.toml").splitlines(keepends=True)
        if available_models is not None and not is_codex_native_provider(profile_lines):
            update_owned_model_catalog_models(
                profile_dir,
                available_models,
                native_catalog_dir=config_dir,
            )
        else:
            ensure_model_in_owned_catalog(profile_dir, model, native_catalog_dir=config_dir)
        if original_record.name != name:
            updated_path = rename_backup(config_dir, profile_dir, name).path
        if apply_to_current:
            restore_backup(config_dir, updated_path)
    except (OSError, json.JSONDecodeError, BackupNameError, ConfigConflictError):
        if updated_path != profile_dir and updated_path.exists() and not profile_dir.exists():
            updated_path.rename(profile_dir)
        restore_config_files(profile_dir, profile_snapshot)
        if current_snapshot is not None:
            restore_config_files(config_dir, current_snapshot)
        raise
    return backup_record_from_path(updated_path)


def validate_backup_path(config_dir: Path, backup_dir: Path) -> Path:
    backup_root = (config_dir / "backups").resolve()
    resolved = backup_dir.resolve()
    if resolved.parent != backup_root:
        raise OSError("备份目录不在当前配置的 backups 目录中。")
    return resolved


def rename_backup(config_dir: Path, backup_dir: Path, new_name: str) -> BackupRecord:
    backup_dir = validate_backup_path(config_dir, backup_dir)
    record = backup_record_from_path(backup_dir)
    new_name = validate_backup_name_format(new_name)
    if named_backup_records(config_dir, new_name, exclude_path=backup_dir):
        raise BackupNameConflictError("已存在同名配置，请使用新的配置名称。")
    if record.name == new_name:
        return record

    match = BACKUP_DIR_PATTERN.match(backup_dir.name)
    timestamp = match.group("timestamp") if match else record.created_at.strftime(BACKUP_TIMESTAMP_FORMAT)
    target = backup_dir.parent / f"{timestamp}-{new_name}"
    if target.exists() and normalized_path_key(target) != normalized_path_key(backup_dir):
        raise BackupNameConflictError("目标配置目录已存在，请使用新的配置名称。")
    backup_dir.rename(target)
    return backup_record_from_path(target)


def delete_backups(config_dir: Path, backup_dirs: list[Path]) -> None:
    resolved_dirs = [validate_backup_path(config_dir, backup_dir) for backup_dir in backup_dirs]
    pending = pending_active_profile_path(config_dir)
    for resolved in resolved_dirs:
        if resolved.exists():
            shutil.rmtree(resolved)
    if pending is not None and any(
        normalized_path_key(pending) == normalized_path_key(resolved)
        for resolved in resolved_dirs
    ):
        set_pending_active_profile_path(None)


def drag_selection_items(
    ordered_items: tuple[str, ...],
    anchor: str,
    current: str,
    base_selection: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if anchor not in ordered_items or current not in ordered_items:
        return tuple(item for item in ordered_items if item in base_selection)
    start = ordered_items.index(anchor)
    end = ordered_items.index(current)
    lower, upper = sorted((start, end))
    selected = set(base_selection)
    selected.update(ordered_items[lower : upper + 1])
    return tuple(item for item in ordered_items if item in selected)


def _profile_provider_fields(profile_dir: Path) -> tuple[str, str, str, str]:
    config_path = profile_dir / "config.toml"
    if not config_path.exists():
        raise OSError("选择的配置缺少 config.toml。")
    lines = read_text(config_path).splitlines(keepends=True)
    provider_id = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
    section = f"model_providers.{provider_id}"
    provider_name = get_section_value(lines, section, "name") or provider_id
    base_url = get_section_value(lines, section, "base_url") or DEFAULT_BASE_URL
    model = get_top_level_value(lines, "model") or TEMPLATE_MODEL
    return provider_id, provider_name, base_url, model


def apply_saved_profile(config_dir: Path, backup_dir: Path) -> None:
    """Restore saved launch defaults without replacing Codex private thread state."""
    backup_dir = validate_backup_path(config_dir, backup_dir)
    source_auth = backup_dir / "auth.json"
    source_config = backup_dir / "config.toml"
    if not (source_auth.exists() or source_config.exists()):
        raise OSError("选择的配置不包含可使用的配置文件。")
    snapshot = capture_config_files(config_dir)
    try:
        if source_config.exists():
            provider_id, provider_name, base_url, model = _profile_provider_fields(backup_dir)
            source_lines = read_text(source_config).splitlines(keepends=True)
            source_catalog_status, source_catalog_reference = model_catalog_reference(source_lines)
            if provider_id == DEFAULT_PROVIDER and source_catalog_status == "owned":
                source_catalog_status, source_catalog_reference = "none", None
            source_reasoning = get_top_level_value(source_lines, "model_reasoning_effort")
            source_catalog_bytes: bytes | None = None
            if source_catalog_status == "owned":
                source_catalog = read_owned_model_catalog(backup_dir)
                if not any(entry.get("slug") == model for entry in source_catalog["models"]):
                    raise ConfigConflictError("选择的配置模型不在其模型目录中，无法安全切换。")
                native_models = read_codex_native_model_entries(config_dir)
                live_source_catalog = normalize_owned_model_catalog_reasoning(
                    source_catalog,
                    source_lines,
                    native_models,
                )
                source_catalog_bytes = (
                    json.dumps(live_source_catalog, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")

            config_path = config_dir / "config.toml"
            lines = read_text(config_path).splitlines(keepends=True) if config_path.exists() else []
            lines = replace_or_insert_top_level(lines, "model_provider", provider_id)
            lines = replace_or_insert_top_level(lines, "model", model)
            lines = replace_or_insert_top_level(lines, "preferred_auth_method", "apikey")
            if source_reasoning is None:
                lines = remove_top_level_key(lines, "model_reasoning_effort")
            else:
                lines = replace_or_insert_top_level(lines, "model_reasoning_effort", source_reasoning)
            if source_catalog_status == "none":
                lines = remove_top_level_key(lines, "model_catalog_json")
            else:
                lines = replace_or_insert_top_level(
                    lines,
                    "model_catalog_json",
                    source_catalog_reference or MODEL_CATALOG_FILENAME,
                )
            if provider_id != DEFAULT_PROVIDER:
                section = f"model_providers.{provider_id}"
                lines = replace_or_insert_section_value(lines, section, "name", provider_name)
                lines = replace_or_insert_section_value(lines, section, "base_url", base_url)
            write_text(config_path, "".join(lines))

            live_catalog = config_dir / MODEL_CATALOG_FILENAME
            if source_catalog_status == "owned" and source_catalog_bytes is not None:
                atomic_write_bytes(live_catalog, source_catalog_bytes)
            elif live_catalog.exists():
                live_catalog.unlink()
        if source_auth.exists():
            source_data = json.loads(read_text(source_auth))
            if not isinstance(source_data, dict):
                raise ConfigConflictError("备份 auth.json 不是对象结构，无法应用")
            update_auth_json(config_dir / "auth.json", str(source_data.get("OPENAI_API_KEY", "")))
        save_settings(config_dir)
        clear_profile_cache()
    except (OSError, json.JSONDecodeError, ConfigConflictError):
        restore_config_files(config_dir, snapshot)
        clear_profile_cache()
        raise


def restore_backup(config_dir: Path, backup_dir: Path) -> None:
    apply_saved_profile(config_dir, backup_dir)


def switch_saved_profile(
    config_dir: Path,
    backup_dir: Path,
    allow_running_restart: bool = False,
) -> CodexLaunchResult:
    """Close Codex, persist the outgoing profile, project the target, and relaunch."""
    backup_dir = validate_backup_path(config_dir, backup_dir)
    processes = list_windows_processes({"ChatGPT.exe", "codex.exe", "codex-code-mode-host.exe"})
    running_target = codex_restart_target(processes)
    was_running = running_target is not None
    if was_running and not allow_running_restart:
        raise ConfigConflictError("Codex 已开始运行，请重新切换并确认自动重启。")

    launch_target = running_target
    if running_target is not None:
        installed_target = discover_codex_installation()
        if installed_target is not None and installed_target.app_user_model_id:
            launch_target = CodexRestartTarget(
                root_pid=running_target.root_pid,
                executable=running_target.executable,
                app_user_model_id=installed_target.app_user_model_id,
            )
        if not request_codex_normal_exit(launch_target):
            raise CodexRestartError("无法让 Codex 正常退出，配置尚未切换。")
        remove_stale_codex_tray_registration(launch_target)
    else:
        launch_target = discover_codex_installation()
        if launch_target is None:
            raise CodexRestartError("没有检测到 Codex 安装，配置尚未切换。")

    current_snapshot = capture_config_files(config_dir)
    outgoing = resolve_active_profile(config_dir)
    outgoing_snapshot = capture_config_files(outgoing.path) if outgoing is not None else None
    settings_snapshot = SETTINGS_FILE.read_bytes() if SETTINGS_FILE.exists() else None
    configured_active = active_profile_path(config_dir)
    pending_active = pending_active_profile_path(config_dir)
    protect_pending_profile = (
        configured_active is not None
        and pending_active is not None
        and normalized_path_key(configured_active) == normalized_path_key(pending_active)
    )

    def restore_original_state() -> None:
        restore_config_files(config_dir, current_snapshot)
        if outgoing is not None and outgoing_snapshot is not None:
            restore_config_files(outgoing.path, outgoing_snapshot)
        if settings_snapshot is None:
            if SETTINGS_FILE.exists():
                SETTINGS_FILE.unlink()
        else:
            atomic_write_bytes(SETTINGS_FILE, settings_snapshot)
        clear_profile_cache()

    def relaunch_original_after_rollback() -> str | None:
        if not was_running:
            return None
        try:
            launch_codex_application(launch_target, "restart")
        except (CodexRestartError, OSError) as recovery_error:
            return str(recovery_error) or recovery_error.__class__.__name__
        return None

    try:
        if not protect_pending_profile:
            sync_current_to_active_profile(config_dir)
        restore_backup(config_dir, backup_dir)
        set_official_login_mode(config_dir, False)
        set_active_profile_path(backup_dir)
        set_pending_active_profile_path(None)
    except (OSError, json.JSONDecodeError, ConfigConflictError) as exc:
        restore_original_state()
        recovery_error = relaunch_original_after_rollback()
        message = f"切换配置失败，原配置已恢复：{exc}"
        if recovery_error:
            message += f"\n\n原 Codex 重新启动失败：{recovery_error}"
        raise ConfigConflictError(message) from exc

    action = "restart" if was_running else "start"
    try:
        return launch_codex_application(launch_target, action)
    except (CodexRestartError, OSError) as exc:
        # Never overwrite configuration underneath a partially launched Codex.
        if is_codex_application_running():
            raise CodexRestartError(
                f"配置已切换，但 Codex 启动不完整：{exc}\n\n"
                "请先从任务栏或系统托盘退出 Codex，再手动启动。"
            ) from exc
        restore_original_state()
        recovery_error = relaunch_original_after_rollback()
        message = f"Codex 启动失败，原配置已恢复：{exc}"
        if recovery_error:
            message += f"\n\n原 Codex 重新启动失败：{recovery_error}"
        raise CodexRestartError(message) from exc


def normalize_provider(provider: str, base_url: str) -> str:
    provider = provider.strip() or DEFAULT_PROVIDER
    base_url = base_url.strip() or DEFAULT_BASE_URL
    if provider == DEFAULT_PROVIDER and base_url != DEFAULT_BASE_URL:
        return DEFAULT_CUSTOM_PROVIDER
    return provider


def build_fresh_config_toml(api_key: str, provider: str, base_url: str) -> str:
    provider = normalize_provider(provider, base_url)
    base_url = base_url.strip() or DEFAULT_BASE_URL
    lines = [f"model_provider = {quote_toml_string(provider)}\n"]
    if api_key.strip():
        lines.append('preferred_auth_method = "apikey"\n')
    if provider != DEFAULT_PROVIDER:
        lines.extend(
            [
                "\n",
                f"[model_providers.{provider}]\n",
                f"name = {quote_toml_string(provider)}\n",
                f"base_url = {quote_toml_string(base_url)}\n",
                'wire_api = "responses"\n',
                "requires_openai_auth = true\n",
            ]
        )
    return "".join(lines)


def build_default_config_toml() -> str:
    return f"model_provider = {quote_toml_string(DEFAULT_PROVIDER)}\n"


def build_custom_template_config_toml(provider_name: str, base_url: str, model: str) -> str:
    provider_name = provider_name.strip() or TEMPLATE_PROVIDER_NAME
    base_url = base_url.strip() or TEMPLATE_BASE_URL
    model = model.strip() or TEMPLATE_MODEL
    return "".join(
        [
            f"model_provider = {quote_toml_string(TEMPLATE_PROVIDER_ID)}\n",
            f"model = {quote_toml_string(model)}\n",
            'model_reasoning_effort = "high"\n',
            "disable_response_storage = true\n",
            "\n",
            f"[model_providers.{TEMPLATE_PROVIDER_ID}]\n",
            f"name = {quote_toml_string(provider_name)}\n",
            f"base_url = {quote_toml_string(base_url)}\n",
            'wire_api = "responses"\n',
            "requires_openai_auth = true\n",
            "\n",
            "[features]\n",
            "multi_agent = true\n",
        ]
    )


def update_auth_json(auth_path: Path, api_key: str) -> None:
    auth_data = {}
    if auth_path.exists():
        auth_data = json.loads(read_text(auth_path))
        if not isinstance(auth_data, dict):
            raise ConfigConflictError("auth.json 不是对象结构，无法自动修改")
    if api_key.strip():
        auth_data["OPENAI_API_KEY"] = api_key.strip()
    else:
        auth_data.pop("OPENAI_API_KEY", None)
    write_text(auth_path, json.dumps(auth_data, ensure_ascii=False, indent=2) + "\n")


def find_config_conflicts(config_lines: list[str], provider_id: str, auth_text: str | None) -> list[str]:
    provider_section = f"model_providers.{provider_id}"
    uses_builtin_openai = provider_id == DEFAULT_PROVIDER and count_sections(config_lines, provider_section) == 0
    conflicts = []
    if auth_text is not None and len(re.findall(r'"OPENAI_API_KEY"\s*:', auth_text)) > 1:
        conflicts.append("auth.json 中存在多个 OPENAI_API_KEY")
    if count_top_level_key(config_lines, "model_provider") != 1:
        conflicts.append("config.toml 顶层没有唯一的 model_provider 可供定位")
    if count_top_level_key(config_lines, "preferred_auth_method") > 1:
        conflicts.append("config.toml 顶层存在多个 preferred_auth_method")
    if count_top_level_key(config_lines, "model") != 1:
        conflicts.append("config.toml 顶层没有唯一的 model 可供修改")
    if uses_builtin_openai:
        conflicts.append("当前使用内置 openai provider，没有可安全修改的自定义 Provider 段")
        return conflicts
    if count_sections(config_lines, provider_section) != 1:
        conflicts.append(f"config.toml 中没有唯一的 [{provider_section}] 段可供修改")
    for key in ("name", "base_url"):
        count = count_section_key(config_lines, provider_section, key)
        if count == 0:
            conflicts.append(f"config.toml 的 [{provider_section}] 段没有 {key}")
        elif count > 1:
            conflicts.append(f"config.toml 的 [{provider_section}] 段存在多个 {key}")
    for key in ("wire_api", "requires_openai_auth"):
        count = count_section_key(config_lines, provider_section, key)
        if count > 1:
            conflicts.append(f"config.toml 的 [{provider_section}] 段存在多个 {key}")
    return conflicts


def model_provider_sections(lines: list[str]) -> list[str]:
    sections = []
    for line in lines:
        section = section_name_from_line(line)
        if section and section.startswith("model_providers."):
            sections.append(section)
    return sections


def classify_config_for_editing(config_dir: Path) -> tuple[str, list[str]]:
    config_path = config_dir / "config.toml"
    if not config_path.exists():
        return "needs_template", []

    config_text = read_text(config_path)
    security_issues = validate_config_security(config_text)
    if security_issues:
        return "conflict", security_issues
    lines = config_text.splitlines(keepends=True)
    provider_count = count_top_level_key(lines, "model_provider")
    provider_sections = model_provider_sections(lines)
    if provider_count == 0 and not provider_sections:
        return "needs_template", []
    if provider_count != 1:
        return "conflict", ["config.toml 顶层没有唯一的 model_provider"]

    provider_id = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
    provider_section = f"model_providers.{provider_id}"
    if provider_id == DEFAULT_PROVIDER and count_sections(lines, provider_section) == 0:
        if provider_sections:
            return "conflict", ["当前使用内置 openai，但配置中还存在其它自定义 Provider 段"]
        return "needs_template", []

    auth_path = config_dir / "auth.json"
    auth_text = read_text(auth_path) if auth_path.exists() else None
    conflicts = find_config_conflicts(lines, provider_id, auth_text)
    return ("conflict", conflicts) if conflicts else ("editable", [])

def update_existing_config_toml(config_path: Path, display_name: str, base_url: str, model: str) -> None:
    lines = read_text(config_path).splitlines(keepends=True)
    provider_id = get_top_level_value(lines, "model_provider") or DEFAULT_PROVIDER
    provider_section = f"model_providers.{provider_id}"
    lines = replace_existing_top_level(lines, "model", model.strip() or TEMPLATE_MODEL)
    lines = replace_existing_section_value(lines, provider_section, "name", display_name)
    lines = replace_existing_section_value(lines, provider_section, "base_url", base_url.strip() or DEFAULT_BASE_URL)
    write_text(config_path, "".join(lines))


def update_config_model(config_path: Path, model: str) -> None:
    model = model.strip()
    if not model:
        raise ConfigConflictError("Model 不能为空。")
    if not config_path.exists():
        raise ConfigConflictError("当前配置缺少 config.toml。")

    config_text = read_text(config_path)
    security_issues = validate_config_security(config_text)
    lines = config_text.splitlines(keepends=True)
    if security_issues:
        raise ConfigConflictError("无法安全保存当前配置：\n\n" + "\n".join(f"- {item}" for item in security_issues))
    if count_top_level_key(lines, "model") != 1:
        raise ConfigConflictError("config.toml 顶层没有唯一的 model 可供修改。")
    write_text(config_path, "".join(replace_existing_top_level(lines, "model", model)))


def save_active_model(config_dir: Path, model: str) -> BackupRecord | None:
    """Update the active model without discarding the provider's complete catalog."""
    model = model.strip()
    current_config = read_codex_config(config_dir)
    active_profile = resolve_active_profile(config_dir)
    if model == current_config.model:
        return active_profile

    current_snapshot = capture_config_files(config_dir)
    profile_snapshot = capture_config_files(active_profile.path) if active_profile is not None else None
    try:
        update_config_model(config_dir / "config.toml", model)
        ensure_model_in_owned_catalog(config_dir, model, native_catalog_dir=config_dir)
        if active_profile is not None:
            update_config_model(active_profile.path / "config.toml", model)
            ensure_model_in_owned_catalog(
                active_profile.path,
                model,
                native_catalog_dir=config_dir,
            )
    except (OSError, ConfigConflictError):
        restore_config_files(config_dir, current_snapshot)
        if active_profile is not None and profile_snapshot is not None:
            restore_config_files(active_profile.path, profile_snapshot)
        raise
    finally:
        clear_profile_cache()
    return active_profile


def save_codex_config(
    config_dir: Path,
    api_key: str,
    display_name: str,
    base_url: str,
    model: str,
    model_display_name: str = "",
    persist_settings: bool = True,
    native_catalog_dir: Path | None = None,
) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    base_url = base_url.strip() or DEFAULT_BASE_URL

    auth_path = config_dir / "auth.json"
    config_path = config_dir / "config.toml"
    auth_text = read_text(auth_path) if auth_path.exists() else None
    config_text = read_text(config_path) if config_path.exists() else ""
    security_issues = validate_config_security(config_text) if config_text else []
    if security_issues:
        raise ConfigConflictError("无法安全保存当前配置：\n\n" + "\n".join(f"- {item}" for item in security_issues))
    config_lines = config_text.splitlines(keepends=True) if config_text else []
    previous_model = get_top_level_value(config_lines, "model") or ""
    provider_id = get_top_level_value(config_lines, "model_provider") or DEFAULT_PROVIDER
    conflicts = find_config_conflicts(config_lines, provider_id, auth_text)
    if conflicts:
        raise ConfigConflictError(
            "检测到配置里有重复项，或当前配置没有可安全修改的自定义 Provider 段。\n\n"
            + "\n".join(f"- {item}" for item in conflicts)
            + "\n\n普通保存不会修改 model_provider 或重命名 Provider 段，以避免影响 Codex 聊天窗口状态。"
        )

    snapshot = capture_config_files(config_dir)
    try:
        update_auth_json(auth_path, api_key)
        update_existing_config_toml(config_path, display_name, base_url, model)
        catalog_status, _catalog_reference = model_catalog_reference(config_lines)
        if model_display_name.strip():
            update_owned_model_catalog(
                config_dir,
                model_display_name,
                native_catalog_dir=native_catalog_dir,
            )
        elif catalog_status == "owned":
            ensure_model_in_owned_catalog(
                config_dir,
                model,
                native_catalog_dir=native_catalog_dir,
            )
        if persist_settings:
            save_settings(config_dir)
    except OSError:
        restore_config_files(config_dir, snapshot)
        raise


def restore_default_config(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    snapshot = capture_config_files(config_dir)
    try:
        auth_path = config_dir / "auth.json"
        if auth_path.exists():
            update_auth_json(auth_path, "")
        config_path = config_dir / "config.toml"
        lines = read_text(config_path).splitlines(keepends=True) if config_path.exists() else []
        lines = replace_or_insert_top_level(lines, "model_provider", DEFAULT_PROVIDER)
        lines = remove_top_level_key(lines, "preferred_auth_method")
        write_text(config_path, "".join(lines))
        update_owned_model_catalog(config_dir, "")
        save_settings(config_dir)
    except (OSError, json.JSONDecodeError):
        restore_config_files(config_dir, snapshot)
        raise


def create_custom_template_config(
    config_dir: Path,
    api_key: str | None,
    provider_name: str,
    base_url: str,
    model: str,
    persist_settings: bool = True,
) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    snapshot = capture_config_files(config_dir)
    auth_path = config_dir / "auth.json"
    try:
        if api_key is None:
            if not auth_path.exists():
                write_text(auth_path, "{}\n")
        else:
            update_auth_json(auth_path, api_key)
        write_text(config_dir / "config.toml", build_custom_template_config_toml(provider_name, base_url, model))
        update_owned_model_catalog(config_dir, "")
        if persist_settings:
            save_settings(config_dir)
    except OSError:
        restore_config_files(config_dir, snapshot)
        raise


def save_custom_provider_config(
    config_dir: Path,
    api_key: str,
    provider_name: str,
    base_url: str,
    model: str,
    model_display_name: str = "",
    persist_settings: bool = True,
    native_catalog_dir: Path | None = None,
) -> None:
    """Add a custom Provider while preserving unrelated current settings."""
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    if not config_path.exists():
        create_custom_template_config(
            config_dir,
            api_key,
            provider_name,
            base_url,
            model,
            persist_settings=persist_settings,
        )
        update_owned_model_catalog(
            config_dir,
            model_display_name,
            native_catalog_dir=native_catalog_dir,
        )
        return

    lines = read_text(config_path).splitlines(keepends=True)
    previous_model = get_top_level_value(lines, "model") or ""
    lines = replace_or_insert_top_level(lines, "model_provider", TEMPLATE_PROVIDER_ID)
    lines = replace_or_insert_top_level(lines, "model", model.strip() or TEMPLATE_MODEL)
    provider_section = f"model_providers.{TEMPLATE_PROVIDER_ID}"
    if count_sections(lines, provider_section):
        lines = replace_or_insert_section_value(lines, provider_section, "name", provider_name)
        lines = replace_or_insert_section_value(lines, provider_section, "base_url", base_url)
    else:
        lines = append_provider_section(lines, TEMPLATE_PROVIDER_ID, base_url, provider_name)

    update_auth_json(config_dir / "auth.json", api_key)
    write_text(config_path, "".join(lines))
    catalog_status, _catalog_reference = model_catalog_reference(lines)
    if model_display_name.strip():
        update_owned_model_catalog(
            config_dir,
            model_display_name,
            native_catalog_dir=native_catalog_dir,
        )
    elif catalog_status == "owned":
        ensure_model_in_owned_catalog(
            config_dir,
            model,
            native_catalog_dir=native_catalog_dir,
        )
    if persist_settings:
        save_settings(config_dir)


def create_profile_from_current_config(
    source_dir: Path,
    profile_dir: Path,
    api_key: str,
    provider_name: str,
    base_url: str,
    model: str,
    state: str,
    model_display_name: str = "",
    available_models: list[str] | None = None,
) -> None:
    """Clone safe current settings without inheriting another provider's model catalog."""
    copy_config_files(source_dir, profile_dir)
    profile_config = profile_dir / "config.toml"
    if profile_config.exists():
        profile_lines = read_text(profile_config).splitlines(keepends=True)
        write_text(profile_config, "".join(remove_top_level_key(profile_lines, "model_catalog_json")))
    owned_catalog = profile_dir / MODEL_CATALOG_FILENAME
    if owned_catalog.exists():
        owned_catalog.unlink()
    if state == "editable":
        save_codex_config(
            profile_dir,
            api_key,
            provider_name,
            base_url,
            model,
            model_display_name=model_display_name,
            persist_settings=False,
            native_catalog_dir=source_dir,
        )
    else:
        save_custom_provider_config(
            profile_dir,
            api_key,
            provider_name,
            base_url,
            model,
            model_display_name=model_display_name,
            persist_settings=False,
            native_catalog_dir=source_dir,
        )
    if available_models is not None:
        update_owned_model_catalog_models(
            profile_dir,
            available_models,
            native_catalog_dir=source_dir,
        )


def build_requested_signature(
    config_dir: Path,
    api_key: str,
    provider_name: str,
    base_url: str,
    model: str,
    state: str,
) -> BackupSignature:
    provider_id = TEMPLATE_PROVIDER_ID
    if state == "editable":
        config_path = config_dir / "config.toml"
        config_lines = read_text(config_path).splitlines(keepends=True)
        provider_id = get_top_level_value(config_lines, "model_provider") or DEFAULT_PROVIDER
    return BackupSignature(
        auth_exists=True,
        config_exists=True,
        provider_id=provider_id,
        provider_name=provider_name.strip() or TEMPLATE_PROVIDER_NAME,
        base_url=base_url.strip() or DEFAULT_BASE_URL,
        model=model.strip() or TEMPLATE_MODEL,
        api_key=api_key.strip(),
    )


def save_config_profile(
    config_dir: Path,
    api_key: str,
    provider_name: str,
    base_url: str,
    model: str,
    state: str,
    config_name: str | None,
    model_display_name: str = "",
) -> BackupResult:
    signature = build_requested_signature(config_dir, api_key, provider_name, base_url, model, state)
    existing = find_matching_backup(config_dir, signature)
    if existing is not None:
        snapshot = capture_config_files(config_dir)
        try:
            if state == "needs_template":
                restore_backup(config_dir, existing.path)
            else:
                save_codex_config(config_dir, api_key, provider_name, base_url, model, model_display_name=model_display_name)
        except (OSError, json.JSONDecodeError):
            restore_config_files(config_dir, snapshot)
            raise
        return BackupResult(status="existing", record=existing)
    if config_name is None:
        raise BackupNameError("新增配置必须先填写配置名称。")

    validate_new_backup_name(config_dir, config_name)
    snapshot = capture_config_files(config_dir)
    try:
        if state == "needs_template":
            save_custom_provider_config(config_dir, api_key, provider_name, base_url, model, model_display_name=model_display_name)
        else:
            save_codex_config(config_dir, api_key, provider_name, base_url, model, model_display_name=model_display_name)
        record = create_named_backup(config_dir, config_name)
    except (OSError, json.JSONDecodeError, BackupNameError):
        restore_config_files(config_dir, snapshot)
        raise
    return BackupResult(status="created", record=record)

def scan_common_locations() -> list[Path]:
    found = []
    seen = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved).lower()
        if key not in seen and is_codex_config_dir(resolved):
            seen.add(key)
            found.append(resolved)

    for candidate in candidate_config_dirs():
        add(candidate)

    search_roots = [
        Path.home(),
        Path(os.environ.get("APPDATA", "")),
        Path(os.environ.get("LOCALAPPDATA", "")),
        Path.home() / "Desktop",
    ]
    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        root_depth = len(root.parts)
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.parts) - root_depth
            if depth > 4:
                dirs[:] = []
                continue
            if "auth.json" in files or "config.toml" in files:
                add(current_path)
            dirs[:] = [item for item in dirs if item not in {"node_modules", ".git", "sessions", "archived_sessions", "tmp"}]
    return found


class CodexConfigApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.overrideredirect(True)
        self.resizable(False, False)
        self.configure(bg="#f3f4f7")
        self.path_var = tk.StringVar()
        self.provider_var = tk.StringVar(value=DEFAULT_PROVIDER)
        self.base_url_var = tk.StringVar(value=DEFAULT_BASE_URL)
        self.model_var = tk.StringVar(value=TEMPLATE_MODEL)
        self.model_display_name_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)
        self._update_check_in_progress = False
        self._available_update: UpdateInfo | None = None
        self._title_button_drawers: dict[str, object] = {}
        self.status_var = tk.StringVar(value="请选择 Codex 配置目录")
        self.current_config_name_var = tk.StringVar(value="未保存配置")
        self.current_config_prefix_var = tk.StringVar(value="")
        self.current_config_suffix_var = tk.StringVar(value="")
        self.official_status_var = tk.StringVar(value="当前未使用官方登录模式")
        self.profile_search_var = tk.StringVar()
        self.profile_sort_desc = False
        self.profile_switch_in_progress = False
        self.pages: dict[str, tk.Frame] = {}
        self.nav_items: dict[str, tuple[tk.Frame, tk.Label, tk.Button]] = {}
        self.active_page = "current"
        self._window_drag: tuple[int, int, int, int] | None = None
        self._window_drag_latest: tuple[int, int] | None = None
        self._window_drag_job: str | None = None
        self._minimized = False
        self._native_hwnd: int | None = None
        self._native_wndproc = None
        self._original_wndproc: int | None = None
        self.app_icon_image = self._load_ui_image(APP_ICON_PNG_NAME)
        self.title_icon_image = self._load_ui_image(TITLE_ICON_PNG_NAME)
        self.title_button_images = {
            "about": self._load_ui_image(TITLE_ABOUT_ICON_NAME),
            "minimize": self._load_ui_image(TITLE_MINIMIZE_ICON_NAME),
            "close": self._load_ui_image(TITLE_CLOSE_ICON_NAME),
        }
        self.eye_icon = self._load_ui_image(EYE_ICON_NAME)
        self.eye_off_icon = self._load_ui_image(EYE_OFF_ICON_NAME)
        self.about_mark_image = self._load_ui_image(ABOUT_MARK_PNG_NAME)
        self.arkapi_icon_image = self._load_ui_image(ARKAPI_ICON_NAME)
        self.jm2api_icon_image = self._load_ui_image(JM2API_ICON_NAME)
        try:
            self.iconbitmap(str(resource_path(APP_ICON_ICO_NAME)))
        except (OSError, tk.TclError):
            pass
        if self.title_icon_image is not None:
            self.iconphoto(False, self.title_icon_image)
        self.donation_thumbnail = self._load_ui_image(DONATION_THUMBNAIL_IMAGE_NAME)
        self.donation_dialog_image = self._load_ui_image(DONATION_DIALOG_IMAGE_NAME)
        self._build_style()
        self._build_ui()
        self._center_main_window()
        self.bind("<Map>", self._restore_custom_frame, add="+")
        self.bind("<Unmap>", self._track_window_minimized, add="+")
        self.bind("<Alt-F4>", lambda _event: self.destroy())
        self.bind(
            "<Control-a>",
            lambda _event: self._toggle_profile_select_all()
            if self.active_page == "profiles" and self.profile_multi_mode
            else None,
        )
        self.bind(
            "<Escape>",
            lambda _event: self._set_profile_multi_mode(False)
            if self.active_page == "profiles" and self.profile_multi_mode
            else None,
        )
        self.after(50, self._set_appwindow_style)
        self._load_initial_path()
        self.after(150, self.show_onboarding_dialog)
        self.after(1200, self.check_for_updates_on_startup)

    def _load_ui_image(self, name: str) -> tk.PhotoImage | None:
        try:
            return tk.PhotoImage(file=str(resource_path(name)))
        except (OSError, tk.TclError):
            return None

    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f3f4f7")
        style.configure("Panel.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f3f4f7", foreground="#20242b", font=("Microsoft YaHei UI", 9))
        style.configure("Panel.TLabel", background="#ffffff", foreground="#20242b", font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background="#f3f4f7", foreground="#15181e", font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("Hint.TLabel", background="#f3f4f7", foreground="#69707d", font=("Microsoft YaHei UI", 8))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(10, 6), relief="flat", borderwidth=1, background="#ffffff", foreground="#303640")
        style.configure("Compact.TButton", font=("Microsoft YaHei UI", 9), padding=(8, 5), relief="flat", borderwidth=1, background="#edf0f2", foreground="#303640")
        style.configure(
            "Secondary.TButton",
            font=("Microsoft YaHei UI", 9),
            padding=(8, 5),
            relief="flat",
            borderwidth=0,
            background="#e8ecef",
            foreground="#303640",
            bordercolor="#e8ecef",
            lightcolor="#e8ecef",
            darkcolor="#e8ecef",
            focuscolor="#e8ecef",
        )
        style.configure("TButton", bordercolor="#d8dde3", lightcolor="#ffffff", darkcolor="#ffffff")
        style.configure("Compact.TButton", bordercolor="#d8dde3", lightcolor="#ffffff", darkcolor="#ffffff")
        style.map("TButton", background=[("active", "#f4f6f7"), ("disabled", "#eceff1")], foreground=[("disabled", "#a0a6ad")])
        style.map("Compact.TButton", background=[("active", "#e2e6e9"), ("disabled", "#eceff1")], foreground=[("disabled", "#a0a6ad")])
        style.map(
            "Secondary.TButton",
            background=[("pressed", "#d7dde1"), ("active", "#dfe4e7"), ("disabled", "#eceff1")],
            bordercolor=[("pressed", "#d7dde1"), ("active", "#dfe4e7")],
            lightcolor=[("pressed", "#d7dde1"), ("active", "#dfe4e7")],
            darkcolor=[("pressed", "#d7dde1"), ("active", "#dfe4e7")],
            foreground=[("disabled", "#a0a6ad")],
        )
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 9, "bold"), padding=(12, 6), relief="flat", borderwidth=0, background="#2f6f5e", foreground="#ffffff")
        style.map("Primary.TButton", background=[("active", "#285f51"), ("disabled", "#aeb8b4")])
        style.configure("Danger.TButton", font=("Microsoft YaHei UI", 9), padding=(10, 6), foreground="#a33a32")
        style.configure("TEntry", padding=6, relief="flat", borderwidth=1)
        style.configure("Readonly.TEntry", padding=6, fieldbackground="#f7f8f9", foreground="#343a43")
        style.configure(
            "Model.TCombobox",
            padding=(6, 5, 34, 5),
            fieldbackground="#f7f8f9",
            foreground="#343a43",
            borderwidth=1,
            bordercolor="#a8adb2",
            lightcolor="#a8adb2",
            darkcolor="#a8adb2",
            relief="flat",
        )
        style.layout(
            "Model.TCombobox",
            [
                (
                    "Combobox.field",
                    {
                        "sticky": "nswe",
                        "children": [
                            (
                                "Combobox.padding",
                                {
                                    "expand": "1",
                                    "sticky": "nswe",
                                    "children": [("Combobox.textarea", {"sticky": "nswe"})],
                                },
                            )
                        ],
                    },
                )
            ],
        )
        style.map(
            "Model.TCombobox",
            fieldbackground=[("readonly", "#f7f8f9")],
            foreground=[("disabled", "#9aa0a8")],
        )
        style.configure(
            "ComboboxPopdownFrame",
            background="#a8adb2",
            bordercolor="#a8adb2",
            lightcolor="#a8adb2",
            darkcolor="#a8adb2",
            borderwidth=1,
            relief="flat",
        )
        self.option_add("*TCombobox*Listbox.background", "#ffffff")
        self.option_add("*TCombobox*Listbox.foreground", "#303640")
        self.option_add("*TCombobox*Listbox.selectBackground", "#2f6f5e")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.relief", "flat")
        self.option_add("*TCombobox*Listbox.borderWidth", 0)
        self.option_add("*TCombobox*Listbox.highlightThickness", 1)
        self.option_add("*TCombobox*Listbox.highlightBackground", "#a8adb2")
        self.option_add("*TCombobox*Listbox.highlightColor", "#a8adb2")
        self.option_add("*TCombobox*Listbox.font", "{Microsoft YaHei UI} 9")
        style.configure("Key.TEntry", padding=(6, 6, 36, 6), relief="flat", borderwidth=1)
        style.configure(
            "ReadonlyKey.TEntry",
            padding=(6, 6, 36, 6),
            relief="flat",
            borderwidth=1,
            fieldbackground="#f7f8f9",
            foreground="#343a43",
        )
        style.configure("Treeview", rowheight=31, font=("Microsoft YaHei UI", 9), background="#ffffff", fieldbackground="#ffffff", borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"), padding=(8, 7), background="#eef0f2", foreground="#343a43")
        style.map("Treeview", background=[("selected", "#dce9e4")], foreground=[("selected", "#1d332c")])
        style.layout("Profile.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Profile.Treeview",
            rowheight=31,
            font=("Microsoft YaHei UI", 9),
            background="#ffffff",
            fieldbackground="#ffffff",
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Profile.Treeview",
            background=[("selected", "#dce9e4")],
            foreground=[("selected", "#1d332c")],
        )

    def _enable_fast_key_navigation(self, entry: ttk.Entry) -> None:
        state = {
            "anchor": 0,
            "pointer_x": 0,
            "auto_job": None,
            "animation_job": None,
            "animation_target": None,
        }

        def cancel_animation() -> None:
            job = state["animation_job"]
            if job is not None:
                try:
                    entry.after_cancel(job)
                except tk.TclError:
                    pass
            state["animation_job"] = None
            state["animation_target"] = None

        def animate_view() -> None:
            state["animation_job"] = None
            if not entry.winfo_exists() or state["animation_target"] is None:
                return
            first, _last = entry.xview()
            target = float(state["animation_target"])
            distance = target - first
            if abs(distance) < 0.0004:
                entry.xview_moveto(target)
                state["animation_target"] = None
                return
            entry.xview_moveto(first + distance * 0.34)
            state["animation_job"] = entry.after(12, animate_view)

        def scroll_pixels(pixel_delta: float, animated: bool = True) -> None:
            first, last = entry.xview()
            viewport_width = max(entry.winfo_width() - 41, 1)
            base = float(state["animation_target"]) if state["animation_target"] is not None else first
            target = horizontal_scroll_target(base, base + (last - first), viewport_width, pixel_delta)
            if animated:
                state["animation_target"] = target
                if state["animation_job"] is None:
                    state["animation_job"] = entry.after(1, animate_view)
            else:
                cancel_animation()
                entry.xview_moveto(target)

        def stop_auto_scroll(_event=None) -> None:
            job = state["auto_job"]
            if job is not None:
                try:
                    entry.after_cancel(job)
                except tk.TclError:
                    pass
                state["auto_job"] = None

        def auto_scroll() -> None:
            state["auto_job"] = None
            if not entry.winfo_exists():
                return
            units = horizontal_drag_scroll_units(int(state["pointer_x"]), entry.winfo_width())
            if not units:
                return
            scroll_pixels(units * 3.0, animated=False)
            edge_x = 1 if units < 0 else max(entry.winfo_width() - 2, 1)
            index = entry.index(f"@{edge_x}")
            anchor = int(state["anchor"])
            entry.selection_range(min(anchor, index), max(anchor, index))
            entry.icursor(index)
            state["auto_job"] = entry.after(16, auto_scroll)

        def start_drag(event) -> None:
            stop_auto_scroll()
            cancel_animation()
            state["anchor"] = entry.index(f"@{event.x}")
            state["pointer_x"] = event.x

        def update_drag(event) -> str | None:
            state["pointer_x"] = event.x
            units = horizontal_drag_scroll_units(event.x, entry.winfo_width())
            if units:
                if state["auto_job"] is None:
                    state["auto_job"] = entry.after(16, auto_scroll)
                return "break"
            stop_auto_scroll()
            return None

        def mousewheel(event) -> str:
            delta_steps = event.delta / 120 if event.delta else 0
            if delta_steps:
                scroll_pixels(-delta_steps * 72.0)
            return "break"

        def smooth_keyboard_view(_event=None) -> None:
            before = entry.xview()

            def follow_default_binding() -> None:
                if not entry.winfo_exists():
                    return
                after = entry.xview()
                if abs(after[0] - before[0]) < 0.0004:
                    return
                cancel_animation()
                entry.xview_moveto(before[0])
                state["animation_target"] = after[0]
                state["animation_job"] = entry.after(1, animate_view)

            entry.after_idle(follow_default_binding)

        def destroy_navigation(_event=None) -> None:
            stop_auto_scroll()
            cancel_animation()

        entry.bind("<ButtonPress-1>", start_drag, add="+")
        entry.bind("<B1-Motion>", update_drag, add="+")
        entry.bind("<ButtonRelease-1>", stop_auto_scroll, add="+")
        entry.bind("<MouseWheel>", mousewheel, add="+")
        entry.bind("<Shift-MouseWheel>", mousewheel, add="+")
        entry.bind("<KeyPress>", smooth_keyboard_view, add="+")
        entry.bind("<Destroy>", destroy_navigation, add="+")

    def _build_ui(self) -> None:
        shell = tk.Frame(self, bg="#f3f4f7", width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        shell.pack(fill="both", expand=True)
        shell.pack_propagate(False)

        title_bar = tk.Frame(shell, bg="#000000", height=38)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        title_left = tk.Frame(title_bar, bg="#000000")
        title_left.pack(side="left", fill="y", padx=(10, 0))
        icon_label = tk.Label(title_left, image=self.title_icon_image, bg="#000000", borderwidth=0)
        icon_label.pack(side="left", padx=(0, 7))
        icon_label.bind("<ButtonPress-1>", self._start_window_move)
        icon_label.bind("<B1-Motion>", self._move_window)
        title_label = tk.Label(
            title_left,
            text=APP_NAME,
            bg="#000000",
            fg="#f4f4f4",
            font=("Microsoft YaHei UI", 9),
        )
        title_label.pack(side="left")

        close_button = self._title_icon_button(title_bar, "close", self.destroy)
        close_button.pack(side="right", fill="y")
        minimize_button = self._title_icon_button(title_bar, "minimize", self._minimize_window)
        minimize_button.pack(side="right", fill="y")
        self.about_button = self._title_icon_button(title_bar, "about", self.show_about_dialog)
        self.about_button.pack(side="right", fill="y")
        Tooltip(self.about_button, "关于软件")
        for widget in (title_bar, title_left, title_label):
            widget.bind("<ButtonPress-1>", self._start_window_move)
            widget.bind("<B1-Motion>", self._move_window)
            widget.bind("<ButtonRelease-1>", self._stop_window_move)

        body = tk.Frame(shell, bg="#f3f4f7")
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg="#5b5b5b", width=142)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        nav = tk.Frame(sidebar, bg="#5b5b5b")
        nav.pack(fill="x", pady=(26, 0))
        for key, text in (
            ("current", "当前配置"),
            ("profiles", "切换配置"),
            ("official", "官方登录"),
        ):
            self._create_nav_item(nav, key, text)
        self._create_nav_item(nav, "guide", "新手引导")
        self._create_nav_item(nav, "recommended", "推荐渠道")

        if self.donation_thumbnail is not None:
            donation_button = tk.Button(
                sidebar,
                image=self.donation_thumbnail,
                command=self.show_donation_dialog,
                bg="#5b5b5b",
                activebackground="#666666",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                cursor="hand2",
                padx=0,
                pady=0,
            )
            donation_button.pack(side="bottom", pady=(0, 15))
            Tooltip(donation_button, "赞赏作者")

        main = tk.Frame(body, bg="#f3f4f7")
        main.pack(side="left", fill="both", expand=True)
        self.page_host = tk.Frame(main, bg="#f3f4f7")
        self.page_host.pack(fill="both", expand=True)

        self._build_current_page()
        self._build_profiles_page()
        self._build_official_page()
        self._build_guide_page()
        self._build_recommended_page()
        self.show_page("current")

    @staticmethod
    def _draw_app_mark(canvas: tk.Canvas, color: str) -> None:
        canvas.delete("all")
        width = int(canvas.cget("width"))
        height = int(canvas.cget("height"))
        stroke = max(1, round(width / 13))
        x0, x1 = stroke, width - stroke
        pill_height = max(5, round(height * 0.34))
        top_y0, top_y1 = stroke, stroke + pill_height
        bottom_y1 = height - stroke
        bottom_y0 = bottom_y1 - pill_height

        def pill(y0: int, y1: int, dot_right: bool) -> None:
            radius = (y1 - y0) / 2
            canvas.create_arc(x0, y0, x0 + radius * 2, y1, start=90, extent=180, style="arc", outline=color, width=stroke)
            canvas.create_arc(x1 - radius * 2, y0, x1, y1, start=270, extent=180, style="arc", outline=color, width=stroke)
            canvas.create_line(x0 + radius, y0, x1 - radius, y0, fill=color, width=stroke)
            canvas.create_line(x0 + radius, y1, x1 - radius, y1, fill=color, width=stroke)
            dot_x = x1 - radius if dot_right else x0 + radius
            dot_r = max(1.2, radius * 0.32)
            canvas.create_oval(dot_x - dot_r, (y0 + y1) / 2 - dot_r, dot_x + dot_r, (y0 + y1) / 2 + dot_r, fill=color, outline="")

        pill(top_y0, top_y1, True)
        pill(bottom_y0, bottom_y1, False)

    def _title_icon_button(self, parent: tk.Misc, kind: str, command) -> tk.Canvas:
        canvas = tk.Canvas(parent, width=42, height=38, bg="#000000", highlightthickness=0, cursor="hand2")
        current_background = "#000000"

        def draw(background: str | None = None) -> None:
            nonlocal current_background
            if background is not None:
                current_background = background
            canvas.configure(bg=current_background)
            canvas.delete("all")
            image = self.title_button_images[kind]
            if image is not None:
                canvas.create_image(21, 19, image=image, anchor="center")
            if kind == "about" and self._available_update is not None:
                canvas.create_oval(27, 7, 35, 15, fill="#e53935", outline=current_background, width=2)

        hover = "#c42b1c" if kind == "close" else "#292929"
        canvas.bind("<Enter>", lambda _event: draw(hover))
        canvas.bind("<Leave>", lambda _event: draw("#000000"))
        canvas.bind("<Button-1>", lambda _event: command())
        self._title_button_drawers[kind] = draw
        draw()
        return canvas

    def _set_available_update(self, update: UpdateInfo | None) -> None:
        self._available_update = update
        draw_about = self._title_button_drawers.get("about")
        if callable(draw_about):
            draw_about()

    def _draw_eye(self, widget: tk.Label, hidden: bool = False) -> None:
        image = self.eye_off_icon if hidden else self.eye_icon
        widget.configure(image=image)
        widget.image = image

    def _eye_button(self, parent: tk.Misc, command, background: str, hidden: bool = False) -> tk.Label:
        label = tk.Label(parent, bg=background, borderwidth=0, cursor="hand2")
        self._draw_eye(label, hidden)
        label.bind("<Button-1>", lambda _event: command())
        return label

    def _create_nav_item(self, parent: tk.Misc, key: str, text: str) -> None:
        row = tk.Frame(parent, bg="#5b5b5b", height=42)
        row.pack(fill="x")
        row.pack_propagate(False)
        indicator = tk.Label(row, bg="#5b5b5b", width=1)
        indicator.pack(side="left", fill="y")
        button = tk.Button(
            row,
            text=text,
            command=lambda: self.show_page(key),
            bg="#5b5b5b",
            fg="#ffffff",
            activebackground="#6a6a6a",
            activeforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            anchor="w",
            padx=24,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        button.pack(side="left", fill="both", expand=True)
        self.nav_items[key] = (row, indicator, button)

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.active_page = key
        page.tkraise()
        for item_key, (row, indicator, button) in self.nav_items.items():
            selected = item_key == key
            background = "#eceeef" if selected else "#5b5b5b"
            foreground = "#20242b" if selected else "#ffffff"
            row.configure(bg=background)
            indicator.configure(bg="#2f6f5e" if selected else "#5b5b5b")
            button.configure(bg=background, fg=foreground, activebackground=background, activeforeground=foreground)
        if key == "profiles":
            self.refresh_profiles()
        elif key == "official":
            self._refresh_official_page()

    def _new_page(self, key: str) -> tk.Frame:
        page = tk.Frame(self.page_host, bg="#f3f4f7")
        page.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.pages[key] = page
        return page

    def _page_header(self, page: tk.Misc, title: str, subtitle: str = "") -> tk.Frame:
        header = tk.Frame(page, bg="#f3f4f7")
        header.pack(fill="x", padx=28, pady=(16, 11))
        tk.Label(header, text=title, bg="#f3f4f7", fg="#171a20", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(header, text=subtitle, bg="#f3f4f7", fg="#69707d", font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(4, 0))
        return header

    def _panel(self, parent: tk.Misc, padding: tuple[int, int] = (14, 12)) -> tk.Frame:
        panel = tk.Frame(parent, bg="#ffffff", highlightthickness=1, highlightbackground="#eceef1")
        panel.pack(fill="x", padx=28, pady=(0, 12))
        inner = tk.Frame(panel, bg="#ffffff", padx=padding[0], pady=padding[1])
        inner.pack(fill="both", expand=True)
        return inner

    def _build_current_page(self) -> None:
        page = self._new_page("current")
        header = tk.Frame(page, bg="#f3f4f7")
        header.pack(fill="x", padx=28, pady=(16, 11))
        title_row = tk.Frame(header, bg="#f3f4f7")
        title_row.pack(fill="x")
        status_dot = tk.Canvas(title_row, width=12, height=25, bg="#f3f4f7", highlightthickness=0)
        status_dot.create_oval(3, 9, 9, 15, fill="#2e9b63", outline="")
        status_dot.pack(side="left", padx=(0, 5))
        status_font = ("Microsoft YaHei UI", 13, "bold")
        tk.Label(title_row, textvariable=self.current_config_prefix_var, bg="#f3f4f7", fg="#20242b", font=status_font, padx=0, borderwidth=0).pack(side="left")
        tk.Label(title_row, textvariable=self.current_config_name_var, bg="#f3f4f7", fg="#20242b", font=status_font, padx=0, borderwidth=0).pack(side="left")
        tk.Label(title_row, textvariable=self.current_config_suffix_var, bg="#f3f4f7", fg="#20242b", font=status_font, padx=0, borderwidth=0).pack(side="left")
        tk.Label(
            header,
            text="欢迎使用Codex配置助手，如果觉得软件好用，请点击左侧二维码并扫描，支持作者。",
            bg="#f3f4f7",
            fg="#69707d",
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", pady=(4, 0))

        path_panel = self._panel(page, (12, 9))
        tk.Label(path_panel, text="Codex 配置目录", bg="#ffffff", fg="#2a3038", font=("Microsoft YaHei UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
        path_row = tk.Frame(path_panel, bg="#ffffff")
        path_row.pack(fill="x")
        ttk.Entry(path_row, textvariable=self.path_var, state="readonly", style="Readonly.TEntry").pack(side="left", fill="x", expand=True, ipady=1)
        ttk.Button(path_row, text="浏览...", command=self.choose_path, style="Secondary.TButton", width=10).pack(side="left", padx=(8, 0), ipady=3)
        ttk.Button(path_row, text="新增配置", command=self._show_profile_editor, style="Secondary.TButton", width=11).pack(side="left", padx=(8, 0), ipady=3)

        details = self._panel(page, (16, 8))
        details.columnconfigure(1, weight=1)
        self.key_entry = self._readonly_field(details, 0, "API Key", self.api_key_var, secret=True)
        self._readonly_field(details, 1, "Provider 显示名称", self.provider_var)
        self._readonly_field(details, 2, "Base URL", self.base_url_var)
        self._readonly_field(details, 3, "启动默认模型", self.model_var)

    def _readonly_field(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, secret: bool = False) -> ttk.Entry:
        tk.Label(parent, text=label, bg="#ffffff", fg="#303640", font=("Microsoft YaHei UI", 9)).grid(row=row, column=0, sticky="w", padx=(0, 18), pady=6)
        field = tk.Frame(parent, bg="#ffffff")
        field.grid(row=row, column=1, sticky="ew", pady=6)
        entry = ttk.Entry(
            field,
            textvariable=variable,
            state="readonly",
            show="*" if secret else "",
            style="ReadonlyKey.TEntry" if secret else "Readonly.TEntry",
        )
        entry.pack(side="left", fill="both", expand=True, ipady=1)
        if secret:
            self._enable_fast_key_navigation(entry)
            self.key_toggle_button = self._eye_button(field, self.toggle_key_visibility, "#f7f8f9")
            self.key_toggle_button.place(relx=1.0, rely=0.5, anchor="e", x=-6, y=0)
        return entry

    def _build_official_page(self) -> None:
        page = self._new_page("official")
        self._page_header(page, "官方登录", "切换到 Codex 官方登录配置，用自己的 ChatGPT/GPT 账号登录。")
        panel = self._panel(page, (20, 18))
        tk.Label(panel, textvariable=self.official_status_var, bg="#ffffff", fg="#20242b", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        tk.Label(
            panel,
            text="切换后不会丢失聊天记录，已保存的 API 配置也会保留。",
            bg="#ffffff",
            fg="#5f6773",
            justify="left",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(12, 18))
        self.official_action_button = ttk.Button(panel, text="进入官方登录模式", command=self.restore_defaults, style="Primary.TButton")
        self.official_action_button.pack(anchor="w")

    def _build_guide_page(self) -> None:
        page = self._new_page("guide")
        self._page_header(page, "新手引导", "配置助手主要提供新增配置和切换配置两个功能。")
        panel = self._panel(page, (20, 15))
        important_model_hint = "供应商是GPT或者OpenAI模型时，无需获取模型"
        sections = (
            ("新增配置", ("打开“新增配置”，填写配置名称、API Key、Provider 显示名称、Base URL 和启动默认模型。", important_model_hint)),
            ("切换配置", ("双击目标配置即可应用并启动 Codex；运行中切换时需确认自动重启。", "编辑正在使用的配置后，也需要双击该配置应用修改。")),
        )
        for title, messages in sections:
            tk.Label(panel, text=title, bg="#ffffff", fg="#20242b", anchor="w", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
            for message in messages:
                message_color = "#8b2f2a" if message == important_model_hint else "#4f5865"
                tk.Label(panel, text="• " + message, bg="#ffffff", fg=message_color, justify="left", anchor="w", wraplength=500, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(0, 7))
            tk.Frame(panel, bg="#eef0f2", height=1).pack(fill="x", pady=(3, 14))

    def _build_recommended_page(self) -> None:
        page = self._new_page("recommended")
        self._page_header(page, "推荐渠道", "精选 API 服务渠道。")
        panel_outer = tk.Frame(page, bg="#ffffff", highlightthickness=1, highlightbackground="#eceef1")
        panel_outer.pack(fill="both", expand=True, padx=28, pady=(0, 28))
        panel = tk.Frame(panel_outer, bg="#ffffff", padx=20, pady=15)
        panel.pack(fill="both", expand=True)

        def add_channel(
            title: str,
            url: str,
            icon_image: tk.PhotoImage | None = None,
            icon_text: str = "",
        ) -> None:
            row = tk.Frame(
                panel,
                bg="#ffffff",
                highlightthickness=1,
                highlightbackground="#e2e5e8",
                highlightcolor="#e2e5e8",
                cursor="hand2",
            )
            row.pack(fill="x", pady=(0, 10))
            icon = tk.Label(
                row,
                text=icon_text,
                bg="#eef5f2",
                fg="#355d52",
                width=4,
                height=2,
                font=("Microsoft YaHei UI", 9, "bold"),
            )
            if icon_image is not None:
                scale = max(1, icon_image.width() // 28)
                if scale > 1:
                    icon_image = icon_image.subsample(scale, scale)
                icon.configure(image=icon_image, text="", width=36, height=36)
                icon.image = icon_image
            icon.pack(side="left", padx=(12, 10), pady=10)
            text_frame = tk.Frame(row, bg="#ffffff")
            text_frame.pack(side="left", fill="x", expand=True, pady=9)
            title_label = tk.Label(
                text_frame,
                text=title,
                bg="#ffffff",
                fg="#20242b",
                anchor="w",
                font=("Microsoft YaHei UI", 10, "bold"),
            )
            title_label.pack(anchor="w")
            address = tk.Label(
                text_frame,
                text=url,
                bg="#ffffff",
                fg="#2f6f5e",
                anchor="w",
                cursor="hand2",
                font=("Microsoft YaHei UI", 9, "underline"),
            )
            address.pack(anchor="w", pady=(3, 0))
            for widget in (row, icon, text_frame, title_label, address):
                widget.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target, new=2))

        add_channel(
            "AI Ark API    更高性价比    快速稳定    隐私安全    价格透明",
            RECOMMENDED_CHANNEL_URL,
            icon_image=self.arkapi_icon_image,
        )
        add_channel("JM2 API", JM2API_CHANNEL_URL, icon_image=self.jm2api_icon_image)

    def _center_main_window(self) -> None:
        x = max((self.winfo_screenwidth() - WINDOW_WIDTH) // 2, 0)
        y = max((self.winfo_screenheight() - WINDOW_HEIGHT) // 2, 0)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def _start_window_move(self, event) -> None:
        self._window_drag = (event.x_root, event.y_root, self.winfo_x(), self.winfo_y())
        self._window_drag_latest = (event.x_root, event.y_root)

    def _move_window(self, event) -> None:
        if self._window_drag is None:
            return
        self._window_drag_latest = (event.x_root, event.y_root)
        if self._window_drag_job is None:
            self._window_drag_job = self.after(8, self._apply_window_move)

    def _apply_window_move(self) -> None:
        self._window_drag_job = None
        if self._window_drag is None or self._window_drag_latest is None:
            return
        start_x, start_y, window_x, window_y = self._window_drag
        current_x, current_y = self._window_drag_latest
        self.geometry(f"+{window_x + current_x - start_x}+{window_y + current_y - start_y}")

    def _stop_window_move(self, _event=None) -> None:
        if self._window_drag_job is not None:
            self.after_cancel(self._window_drag_job)
            self._window_drag_job = None
            self._apply_window_move()
        self._window_drag = None
        self._window_drag_latest = None

    def _minimize_window(self) -> None:
        self._minimized = True
        if os.name == "nt":
            try:
                import ctypes

                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, 6)
                return
            except (AttributeError, OSError):
                pass
        self.overrideredirect(False)
        self.iconify()

    def _restore_custom_frame(self, _event=None) -> None:
        if not self._minimized:
            return
        self.after_idle(self._finish_taskbar_restore)

    def _track_window_minimized(self, _event=None) -> None:
        self.after_idle(self._update_minimized_state)

    def _update_minimized_state(self) -> None:
        if not self.winfo_exists():
            return
        if os.name == "nt":
            try:
                import ctypes

                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
                if ctypes.windll.user32.IsIconic(hwnd):
                    self._minimized = True
                    return
            except (AttributeError, OSError):
                pass
        if self.state() == "iconic":
            self._minimized = True

    def _finish_taskbar_restore(self) -> None:
        if not self.winfo_exists() or self.state() != "normal":
            return
        self._minimized = False
        if os.name != "nt":
            self.overrideredirect(True)
            self._set_appwindow_style()

    def _set_appwindow_style(self) -> None:
        if os.name != "nt" or not self.winfo_exists():
            return
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            was_viewable = bool(self.winfo_viewable())
            if was_viewable:
                self.withdraw()
                self.update_idletasks()
            register_appwindow_with_shell(hwnd, ctypes.windll.user32)
            if was_viewable:
                self.deiconify()
                self.lift()
                self.focus_force()
            self._install_native_frame_handler(hwnd)
        except (AttributeError, OSError):
            pass

    def _install_native_frame_handler(self, hwnd: int) -> None:
        if self._native_hwnd == hwnd and self._native_wndproc is not None:
            return

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = (
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.CallWindowProcW.restype = ctypes.c_ssize_t

        original_wndproc = user32.GetWindowLongPtrW(hwnd, -4)
        if not original_wndproc:
            return

        @wndproc_type
        def custom_wndproc(window, message, wparam, lparam):
            if message == 0x0083 and wparam:
                return 0
            return user32.CallWindowProcW(original_wndproc, window, message, wparam, lparam)

        previous_wndproc = user32.SetWindowLongPtrW(
            hwnd,
            -4,
            ctypes.cast(custom_wndproc, ctypes.c_void_p),
        )
        if not previous_wndproc:
            return
        self._native_hwnd = hwnd
        self._original_wndproc = int(previous_wndproc)
        self._native_wndproc = custom_wndproc

    def _build_profiles_page(self) -> None:
        page = self._new_page("profiles")
        self._page_header(
            page,
            "已保存配置",
            "双击目标配置，软件会保存当前公开设置、切换配置并自动启动 Codex。",
        )

        toolbar = tk.Frame(page, bg="#f3f4f7")
        toolbar.pack(fill="x", padx=28, pady=(0, 10))
        ttk.Button(toolbar, text="打开配置库目录", command=self.open_backup_dir, style="Secondary.TButton").pack(side="left", ipady=3)
        ttk.Button(toolbar, text="新增配置", command=self._show_profile_editor, style="Secondary.TButton").pack(side="left", padx=(8, 0), ipady=3)
        self.profile_switch_button = ttk.Button(
            toolbar,
            text="切换到该配置",
            command=self._switch_selected_profile,
            style="Primary.TButton",
        )
        self.profile_switch_button.pack(side="right", ipady=2)
        search_entry = ttk.Entry(toolbar, textvariable=self.profile_search_var, width=24)
        search_entry.pack(side="right", padx=(0, 10), ipady=1)
        tk.Label(toolbar, text="搜索", bg="#f3f4f7", fg="#5f6773", font=("Microsoft YaHei UI", 8)).pack(side="right", padx=(0, 6))

        self.profile_empty_var = tk.StringVar()
        tk.Label(
            page,
            textvariable=self.profile_empty_var,
            bg="#f3f4f7",
            fg="#69707d",
            anchor="e",
            font=("Microsoft YaHei UI", 8),
        ).pack(fill="x", padx=28, pady=(0, 6))

        tree_panel = tk.Frame(
            page,
            bg="#ffffff",
            highlightthickness=1,
            highlightbackground="#e2e5e8",
            highlightcolor="#e2e5e8",
            takefocus=False,
        )
        tree_panel.pack(fill="both", expand=True, padx=28, pady=(0, STATUS_AREA_HEIGHT))
        tree_frame = tk.Frame(tree_panel, bg="#ffffff")
        tree_frame.pack(fill="both", expand=True)
        self.profile_tree = ttk.Treeview(
            tree_frame,
            columns=("name", "base_url"),
            show="headings",
            selectmode="browse",
            height=7,
            style="Profile.Treeview",
        )
        self.profile_tree.heading("name", text="配置名称  ▲", command=self._toggle_profile_sort)
        self.profile_tree.heading("base_url", text="Base URL")
        self.profile_tree.column("name", width=225, minwidth=165, anchor="w")
        self.profile_tree.column("base_url", width=330, minwidth=220, anchor="w")
        self.profile_tree.tag_configure("active", foreground="#218354")
        scrollbar = FlatVerticalScrollbar(tree_frame, command=self.profile_tree.yview)
        self.profile_tree.configure(yscrollcommand=scrollbar.set)
        self.profile_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.profile_multi_bar = tk.Frame(page, bg="#f3f4f7")
        self.profile_multi_bar.pack(fill="x", padx=28, pady=(0, 8))
        self.profile_select_all_button = ttk.Button(
            self.profile_multi_bar,
            text="全选",
            command=self._toggle_profile_select_all,
            style="Compact.TButton",
        )
        self.profile_select_all_button.pack(side="left")
        self.profile_delete_selected_button = ttk.Button(
            self.profile_multi_bar,
            text="删除所选配置",
            command=lambda: self._delete_profile_records(self._selected_profile_records()),
            style="Danger.TButton",
        )
        self.profile_delete_selected_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            self.profile_multi_bar,
            text="退出多选",
            command=lambda: self._set_profile_multi_mode(False),
            style="Compact.TButton",
        ).pack(side="right")

        self.profile_records_by_item: dict[str, BackupRecord] = {}
        self.profile_multi_mode = False
        self.profile_drag_state = {"active": False, "anchor": None, "base": (), "start_y": 0, "moved": False}
        self.profile_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_profile_buttons())
        self.profile_tree.bind("<Button-3>", self._show_profile_context_menu)
        self.profile_tree.bind("<ButtonPress-1>", self._profile_press, add="+")
        self.profile_tree.bind("<B1-Motion>", self._profile_drag, add="+")
        self.profile_tree.bind("<ButtonRelease-1>", self._profile_release, add="+")
        self.profile_tree.bind("<Double-1>", self._profile_double_click)
        page.bind("<Control-a>", lambda _event: self._toggle_profile_select_all() if self.profile_multi_mode else None)
        self.profile_search_var.trace_add("write", lambda *_args: self.refresh_profiles())
        self._set_profile_multi_mode(False)

    def _selected_profile_records(self) -> list[BackupRecord]:
        return [
            self.profile_records_by_item[item]
            for item in self.profile_tree.selection()
            if item in self.profile_records_by_item
        ]

    def refresh_profiles(self, select_path: Path | None = None) -> None:
        if not hasattr(self, "profile_tree"):
            return
        previous_paths = {
            normalized_path_key(record.path)
            for record in self._selected_profile_records()
        }
        if select_path is not None:
            previous_paths = {normalized_path_key(select_path)}
        self.profile_records_by_item.clear()
        self.profile_tree.delete(*self.profile_tree.get_children())
        query = self.profile_search_var.get().strip().casefold()
        active_record = find_matching_backup(self.current_path())
        active_key = normalized_path_key(active_record.path) if active_record is not None else None
        records = list_backup_records(self.current_path())
        records.sort(key=lambda item: item.name.casefold(), reverse=getattr(self, "profile_sort_desc", False))
        if active_key:
            records.sort(key=lambda item: normalized_path_key(item.path) != active_key)
        selected_items = []
        for index, record in enumerate(records):
            profile_entry = cached_profile_entry(record.path)
            if query and query not in record.name.casefold() and query not in profile_entry.base_url.casefold():
                continue
            item = f"profile-{index}"
            record_key = normalized_path_key(record.path)
            display_name = f"●  {record.name}" if record_key == active_key else record.name
            self.profile_records_by_item[item] = record
            self.profile_tree.insert(
                "",
                "end",
                iid=item,
                values=(display_name, profile_entry.base_url),
                tags=("active",) if record_key == active_key else (),
            )
            if record_key in previous_paths:
                selected_items.append(item)
        if not self.profile_records_by_item:
            self.profile_empty_var.set("没有符合条件的配置。" if query else "暂无已保存配置，可以从当前配置页面新增。")
        else:
            self.profile_empty_var.set(f"共 {len(self.profile_records_by_item)} 个配置")
        if selected_items:
            self.profile_tree.selection_set(selected_items if self.profile_multi_mode else selected_items[:1])
            self.profile_tree.focus(selected_items[0])
        elif self.profile_records_by_item and not self.profile_multi_mode:
            first = next(iter(self.profile_records_by_item))
            self.profile_tree.selection_set(first)
            self.profile_tree.focus(first)
        self._update_profile_buttons()

    def _toggle_profile_sort(self) -> None:
        self.profile_sort_desc = not self.profile_sort_desc
        self.profile_tree.heading("name", text="配置名称  ▼" if self.profile_sort_desc else "配置名称  ▲")
        self.refresh_profiles()

    def _update_profile_buttons(self) -> None:
        if not hasattr(self, "profile_tree"):
            return
        selection_count = len(self._selected_profile_records())
        item_count = len(self.profile_records_by_item)
        self.profile_switch_button.configure(
            state="normal" if selection_count == 1 and not self.profile_multi_mode else "disabled"
        )
        self.profile_delete_selected_button.configure(state="normal" if selection_count else "disabled")
        self.profile_select_all_button.configure(
            text="取消全选" if item_count and selection_count == item_count else "全选",
            state="normal" if item_count else "disabled",
        )

    def _set_profile_multi_mode(self, enabled: bool) -> None:
        self.profile_multi_mode = enabled
        self.profile_tree.configure(selectmode="extended" if enabled else "browse")
        if enabled:
            self.profile_multi_bar.pack(fill="x", padx=28, pady=(0, 8))
        else:
            selection = self.profile_tree.selection()
            if len(selection) > 1:
                self.profile_tree.selection_set(selection[0])
            self.profile_multi_bar.pack_forget()
        self._update_profile_buttons()

    def _toggle_profile_select_all(self) -> str | None:
        if not self.profile_multi_mode:
            return None
        items = self.profile_tree.get_children()
        if items and len(self.profile_tree.selection()) == len(items):
            self.profile_tree.selection_remove(*items)
        else:
            self.profile_tree.selection_set(items)
            if items:
                self.profile_tree.focus(items[0])
        self._update_profile_buttons()
        return "break"

    def _show_profile_context_menu(self, event) -> None:
        item = self.profile_tree.identify_row(event.y)
        if not item or item not in self.profile_records_by_item:
            return
        if self.profile_multi_mode:
            self.profile_tree.selection_add(item)
        else:
            self.profile_tree.selection_set(item)
        self.profile_tree.focus(item)
        self._update_profile_buttons()
        record = self.profile_records_by_item[item]
        menu = tk.Menu(self, tearoff=False)
        if self.profile_multi_mode:
            menu.add_command(
                label="删除所选配置",
                command=lambda: self._delete_profile_records(self._selected_profile_records()),
            )
        else:
            menu.add_command(label="编辑配置", command=lambda: self._show_profile_editor(record))
            menu.add_command(label="删除配置", command=lambda: self._delete_profile_records([record]))
        menu.add_separator()
        menu.add_command(
            label="退出多选" if self.profile_multi_mode else "多选",
            command=lambda: self._set_profile_multi_mode(not self.profile_multi_mode),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _switch_selected_profile(self) -> None:
        records = self._selected_profile_records()
        if len(records) != 1 or self.profile_multi_mode or self.profile_switch_in_progress:
            return
        selected = records[0]
        config_dir = self.current_path()
        selected_key = normalized_path_key(selected.path)
        configured_active = active_profile_path(config_dir)
        pending_active = pending_active_profile_path(config_dir)
        resolved_active = resolve_active_profile(config_dir)
        selected_is_active = any(
            profile is not None and normalized_path_key(profile.path) == selected_key
            for profile in (resolved_active,)
        ) or any(
            path is not None and normalized_path_key(path) == selected_key
            for path in (configured_active, pending_active)
        )
        selected_pending = profile_has_pending_apply(config_dir, selected.path)
        try:
            running = codex_restart_target(
                list_windows_processes({"ChatGPT.exe", "codex.exe", "codex-code-mode-host.exe"})
            ) is not None
        except OSError as exc:
            self.show_error(f"无法检查 Codex 运行状态：\n{exc}")
            return
        if selected_is_active and running and not selected_pending:
            self._notify(f"Codex 已在使用配置：{selected.name}，并且正在运行。")
            return
        if running and not self.ask_yes_no("应用配置需要正常退出并重新启动 Codex，是否继续？"):
            return
        self.profile_switch_in_progress = True
        self._notify(
            f"正在保存当前配置并应用：{selected.name}..."
            if running
            else f"正在应用配置并启动 Codex：{selected.name}..."
        )

        def worker() -> None:
            try:
                result = switch_saved_profile(
                    config_dir,
                    selected.path,
                    allow_running_restart=running,
                )
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
                self.after(0, lambda error=error: self._finish_profile_switch(selected, error))
                return
            self.after(0, lambda: self._finish_profile_switch(selected, None, result.action))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_profile_switch(
        self,
        selected: BackupRecord,
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
        self._notify(
            f"已切换到配置：{selected.name}，Codex 已启动。"
            if action == "start"
            else f"已切换到配置：{selected.name}，Codex 已重新启动。"
        )

    def _profile_double_click(self, event) -> str:
        item = self.profile_tree.identify_row(event.y)
        if not item or item not in self.profile_records_by_item or self.profile_multi_mode:
            return "break"
        self.profile_tree.selection_set(item)
        self.profile_tree.focus(item)
        self._switch_selected_profile()
        return "break"

    def _delete_profile_records(self, records: list[BackupRecord]) -> None:
        if not records:
            return
        if len(records) == 1:
            message = f"确定永久删除“{records[0].name}”吗？\n\n删除后无法恢复。"
        else:
            message = f"确定永久删除所选的 {len(records)} 个配置吗？\n\n删除后无法恢复。"
        if not self.ask_yes_no(message):
            return
        try:
            delete_backups(self.current_path(), [record.path for record in records])
        except OSError as exc:
            self.show_error(f"删除配置失败：\n{exc}")
            return
        self.reload_current()
        self.refresh_profiles()
        self._notify(f"已删除 {len(records)} 个配置。")

    def _profile_press(self, event) -> str | None:
        if not self.profile_multi_mode:
            return None
        item = self.profile_tree.identify_row(event.y)
        if not item:
            return "break"
        self.profile_drag_state = {
            "active": True,
            "anchor": item,
            "base": self.profile_tree.selection(),
            "start_y": event.y,
            "moved": False,
        }
        return "break"

    def _profile_drag(self, event) -> str | None:
        state = self.profile_drag_state
        if not self.profile_multi_mode or not state["active"]:
            return None
        item = self.profile_tree.identify_row(event.y)
        if not item:
            return "break"
        if abs(event.y - state["start_y"]) >= 4 or item != state["anchor"]:
            state["moved"] = True
        if state["moved"]:
            selection = drag_selection_items(
                self.profile_tree.get_children(),
                state["anchor"],
                item,
                state["base"],
            )
            self.profile_tree.selection_set(selection)
            self.profile_tree.focus(item)
            self._update_profile_buttons()
        return "break"

    def _profile_release(self, _event) -> str | None:
        state = self.profile_drag_state
        if not self.profile_multi_mode or not state["active"]:
            return None
        if not state["moved"] and state["anchor"]:
            if state["anchor"] in state["base"]:
                self.profile_tree.selection_remove(state["anchor"])
            else:
                self.profile_tree.selection_add(state["anchor"])
                self.profile_tree.focus(state["anchor"])
        self.profile_drag_state = {"active": False, "anchor": None, "base": (), "start_y": 0, "moved": False}
        self._update_profile_buttons()
        return "break"

    def _show_profile_editor(self, record: BackupRecord | None = None) -> None:
        config_dir = self.current_path()
        source = read_codex_config(record.path if record is not None else config_dir)
        active_record = resolve_active_profile(config_dir)
        configured_active = active_profile_path(config_dir)
        pending_active = pending_active_profile_path(config_dir)
        editing_active = (
            record is not None
            and any(
                path is not None and normalized_path_key(record.path) == normalized_path_key(path)
                for path in (
                    active_record.path if active_record is not None else None,
                    configured_active,
                    pending_active,
                )
            )
        )

        dialog = tk.Toplevel(self)
        dialog.title("编辑配置" if record is not None else "新增配置")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg="#f3f4f7")

        container = tk.Frame(dialog, bg="#f3f4f7", padx=22, pady=18)
        container.pack(fill="both", expand=True)
        title = "编辑配置" if record is not None else "新增配置"
        subtitle = "保存后双击应用；OpenAI 原生模型无需获取列表，“获取模型”仅用于第三方 Provider。"
        tk.Label(container, text=title, bg="#f3f4f7", fg="#171a20", font=("Microsoft YaHei UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(container, text=subtitle, bg="#f3f4f7", fg="#69707d", font=("Microsoft YaHei UI", 8)).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 12))

        name_var = tk.StringVar(value=record.name if record is not None else suggested_config_name(source.provider))
        api_key_var = tk.StringVar(value=source.api_key)
        provider_var = tk.StringVar(value=source.provider or TEMPLATE_PROVIDER_NAME)
        base_url_var = tk.StringVar(value=source.base_url or TEMPLATE_BASE_URL)
        model_var = tk.StringVar(value=source.model or TEMPLATE_MODEL)
        editor_show_key = tk.BooleanVar(value=False)
        fetched_models: list[str] = read_owned_model_catalog_models(record.path) if record is not None else []

        def add_row(row: int, label: str, variable: tk.StringVar, secret: bool = False) -> ttk.Entry:
            tk.Label(container, text=label, bg="#f3f4f7", fg="#303640", font=("Microsoft YaHei UI", 9)).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=6)
            field = tk.Frame(container, bg="#f3f4f7")
            field.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)
            entry = ttk.Entry(
                field,
                textvariable=variable,
                show="*" if secret else "",
                width=48,
                style="Key.TEntry" if secret else "TEntry",
            )
            entry.pack(fill="both", expand=True, ipady=1)
            if secret:
                eye_button = self._eye_button(field, lambda: None, "#ffffff")
                eye_button.place(relx=1.0, rely=0.5, anchor="e", x=-6, y=0)

                def toggle() -> None:
                    visible = not editor_show_key.get()
                    editor_show_key.set(visible)
                    entry.configure(show="" if visible else "*")
                    self._draw_eye(eye_button, hidden=visible)

                eye_button.bind("<Button-1>", lambda _event: toggle())
            return entry

        name_entry = add_row(2, "配置名称", name_var)
        api_key_entry = add_row(3, "API Key", api_key_var, secret=True)
        self._enable_fast_key_navigation(api_key_entry)
        add_row(4, "Provider 显示名称", provider_var)
        add_row(5, "Base URL", base_url_var)
        tk.Label(container, text="启动默认模型", bg="#f3f4f7", fg="#303640", font=("Microsoft YaHei UI", 9)).grid(row=6, column=0, sticky="w", padx=(0, 14), pady=6)
        model_field = tk.Frame(container, bg="#f3f4f7")
        model_field.grid(row=6, column=1, columnspan=2, sticky="ew", pady=6)
        initial_models = list(fetched_models)
        if model_var.get().strip() and model_var.get().strip() not in initial_models:
            initial_models.insert(0, model_var.get().strip())
        model_combo = ttk.Combobox(model_field, textvariable=model_var, values=tuple(initial_models), state="normal", style="Model.TCombobox", width=39)
        model_combo.pack(side="left", fill="both", expand=True, ipady=1)

        model_dropdown_button = tk.Canvas(
            model_field,
            width=28,
            height=29,
            bg="#f7f8f9",
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        model_dropdown_button.place(in_=model_combo, relx=1.0, rely=0.5, anchor="e", x=-1, width=28, height=29)

        def draw_model_dropdown(active: bool = False) -> None:
            model_dropdown_button.configure(bg="#edf0f2" if active else "#f7f8f9")
            model_dropdown_button.delete("all")
            model_dropdown_button.create_line(8, 11, 13, 16, 18, 11, fill="#59616d", width=2, joinstyle="round")
            model_dropdown_button.create_rectangle(27, 0, 28, 29, fill="#a8adb2", outline="")

        def post_model_dropdown(_event=None) -> str:
            model_combo.focus_set()
            try:
                model_combo.tk.call("ttk::combobox::Post", str(model_combo))
            except tk.TclError:
                model_combo.event_generate("<Alt-Down>")
            return "break"

        draw_model_dropdown()
        model_dropdown_button.bind("<Enter>", lambda _event: draw_model_dropdown(True))
        model_dropdown_button.bind("<Leave>", lambda _event: draw_model_dropdown())
        model_dropdown_button.bind("<Button-1>", post_model_dropdown)

        def fetch_editor_models() -> None:
            try:
                fetched_models[:] = fetch_available_models(base_url_var.get().strip(), api_key_var.get())
            except (ModelListError, OSError) as exc:
                error_var.set(str(exc))
                return
            values = list(fetched_models)
            if model_var.get().strip() and model_var.get().strip() not in values:
                values.insert(0, model_var.get().strip())
            model_combo.configure(values=tuple(values))
            model_var.set(values[0] if values else model_var.get())
            error_var.set(f"已获取 {len(fetched_models)} 个模型")

        ttk.Button(model_field, text="获取模型", command=fetch_editor_models, style="Secondary.TButton", width=10).pack(side="left", padx=(8, 0), ipady=3)
        container.columnconfigure(1, weight=1)

        error_var = tk.StringVar()

        def save() -> None:
            provider_name = provider_var.get().strip()
            base_url = base_url_var.get().strip()
            model = model_var.get().strip()
            if not provider_name:
                error_var.set("Provider 显示名称不能为空。")
                return
            if not base_url:
                error_var.set("Base URL 不能为空。")
                return
            if not base_url.startswith(("http://", "https://")):
                error_var.set("Base URL 需要以 http:// 或 https:// 开头。")
                return
            if not model:
                error_var.set("Model 不能为空。")
                return
            try:
                if record is None:
                    saved = create_config_profile(
                        config_dir,
                        name_var.get(),
                        api_key_var.get(),
                        provider_name,
                        base_url,
                        model,
                        apply_to_current=False,
                        available_models=fetched_models if fetched_models else None,
                    )
                else:
                    saved = update_config_profile(
                        config_dir,
                        record.path,
                        name_var.get(),
                        api_key_var.get(),
                        provider_name,
                        base_url,
                        model,
                        apply_to_current=False,
                        available_models=fetched_models if fetched_models else None,
                    )
            except (OSError, json.JSONDecodeError, BackupNameError) as exc:
                error_var.set(str(exc))
                return

            if editing_active:
                set_active_profile_path(saved.path)
                set_pending_active_profile_path(saved.path)
            self.refresh_profiles(saved.path)
            dialog.destroy()
            if editing_active:
                self.load_path(config_dir)
                self._notify(f"已保存修改：{saved.name}；请双击该配置应用。", 3000)
                self.show_info(f"已保存修改“{saved.name}”。\n\n请双击该配置应用并启动或重启 Codex。")
            else:
                self._notify(f"已保存配置：{saved.name}")
                self.show_info(f"已保存配置“{saved.name}”。")

        button_row = tk.Frame(container, bg="#f3f4f7")
        button_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(button_row, text="取消", command=dialog.destroy, style="Compact.TButton", width=9).pack(side="right")
        ttk.Button(
            button_row,
            text="保存修改" if record is not None else "保存配置",
            command=save,
            style="Primary.TButton",
            width=11,
        ).pack(side="right", padx=(0, 8))
        tk.Label(
            button_row,
            textvariable=error_var,
            bg="#f3f4f7",
            fg="#a33a32",
            anchor="w",
            justify="left",
            wraplength=280,
            font=("Microsoft YaHei UI", 8),
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.center_window(dialog, 570, 385)
        name_entry.focus_set()
        name_entry.selection_range(0, "end")

    def _refresh_official_page(self) -> None:
        official = is_official_login_mode(self.current_path())
        if official:
            self.official_status_var.set("当前正在使用官方登录模式")
            self.official_action_button.configure(text="当前已是官方登录模式", state="disabled")
        else:
            self.official_status_var.set("当前正在使用自定义 API 配置")
            self.official_action_button.configure(text="进入官方登录模式", state="normal")

    def center_window(self, window: tk.Toplevel, width: int | None = None, height: int | None = None, parent: tk.Misc | None = None) -> None:
        parent_window = (parent or self).winfo_toplevel()
        parent_window.update_idletasks()
        window.update_idletasks()
        if width is None:
            width = window.winfo_reqwidth()
        if height is None:
            height = window.winfo_reqheight()
        parent_x = parent_window.winfo_rootx()
        parent_y = parent_window.winfo_rooty()
        parent_width = parent_window.winfo_width()
        parent_height = parent_window.winfo_height()
        x = parent_x + max((parent_width - width) // 2, 0)
        y = parent_y + max((parent_height - height) // 2, 0)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.update_idletasks()
        self._style_dialog_window(window)

    def _style_dialog_window(self, window: tk.Toplevel) -> None:
        """Match native dialog chrome to the custom dark title bar on Windows."""
        try:
            window.iconbitmap(str(resource_path(APP_ICON_ICO_NAME)))
        except (OSError, tk.TclError):
            pass
        if os.name != "nt" or not window.winfo_exists():
            return
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            dark_mode = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except (AttributeError, OSError):
            pass

    def focus_for_dialog(self) -> None:
        self.update_idletasks()
        self.lift()
        self.focus_force()

    def _notify(self, message: str, duration: int = 1800) -> None:
        """Show a short-lived, non-blocking status message in the main window."""
        if getattr(self, "_toast", None) is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
        toast = tk.Toplevel(self)
        self._toast = toast
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        transparent_bg = "#f3f4f7"
        toast.configure(bg=transparent_bg)
        if os.name == "nt":
            try:
                toast.attributes("-transparentcolor", transparent_bg)
            except tk.TclError:
                pass
        tk.Label(toast, text=message, bg=transparent_bg, fg="#4f5865", font=("Microsoft YaHei UI", 9)).pack(padx=1, pady=1)
        toast.update_idletasks()
        content_left = 142
        content_width = self.winfo_width() - content_left
        x = self.winfo_rootx() + content_left + max((content_width - toast.winfo_width()) // 2, 8)
        status_top = self.winfo_rooty() + self.winfo_height() - STATUS_AREA_HEIGHT
        y = status_top + max((STATUS_AREA_HEIGHT - toast.winfo_height()) // 2, 0)
        toast.geometry(f"+{x}+{y}")
        toast.after(duration, lambda: toast.winfo_exists() and toast.destroy())

    def show_donation_dialog(self) -> None:
        if self.donation_dialog_image is None:
            self.show_error("赞赏码图片未找到。")
            return

        dialog = tk.Toplevel(self)
        dialog.title("赞赏作者")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg="#f3f4f7")

        container = ttk.Frame(dialog, padding=20)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="感谢你的支持", style="Title.TLabel").pack(pady=(0, 12))
        tk.Label(
            container,
            image=self.donation_dialog_image,
            bg="#ffffff",
            borderwidth=1,
            relief="solid",
        ).pack()

        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.center_window(dialog)
        dialog.focus_force()

    def show_onboarding_dialog(self, force: bool = False) -> None:
        settings = load_settings()
        if not force and not should_show_onboarding(settings):
            return

        dialog = tk.Toplevel(self)
        dialog.title(APP_NAME)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        container = ttk.Frame(dialog, padding=18)
        container.pack(fill="both", expand=True)
        content = ttk.Frame(container)
        content.pack(fill="x", expand=True)
        tk.Label(
            content,
            text="?",
            bg="#2f6f5e",
            fg="#ffffff",
            width=2,
            height=1,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=(0, 14), anchor="n")
        ttk.Label(
            content,
            text="是否打开新手引导？\n\n选择“是”后，将进入新手引导页面。",
            wraplength=380,
            justify="left",
        ).pack(side="left", fill="x", expand=True)

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(18, 0))

        def close(action: str) -> None:
            if action == "never":
                save_setting_value(HIDE_ONBOARDING_KEY, True)
            dialog.destroy()
            if action == "open":
                self.show_page("guide")
            self.lift()
            self.focus_force()

        ttk.Button(button_row, text="不再弹出", command=lambda: close("never"), style="Secondary.TButton", width=10).pack(side="left")
        ttk.Button(button_row, text="否", command=lambda: close("close"), style="Secondary.TButton", width=9).pack(side="right")
        ttk.Button(button_row, text="是", command=lambda: close("open"), style="Secondary.TButton", width=9).pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", lambda: close("close"))
        dialog.bind("<Return>", lambda _event: close("open"))
        dialog.bind("<Escape>", lambda _event: close("close"))
        self.center_window(dialog, 500, 168)
        dialog.focus_force()

    def show_custom_dialog(self, message: str, kind: str = "info", parent: tk.Toplevel | None = None) -> bool:
        target = parent or self
        dialog = tk.Toplevel(target)
        dialog.title(APP_NAME)
        dialog.transient(target)
        dialog.grab_set()
        dialog.resizable(False, False)

        result = {"value": False}
        container = ttk.Frame(dialog, padding=18)
        container.pack(fill="both", expand=True)
        content = ttk.Frame(container)
        content.pack(fill="x", expand=True)

        icon_text = {"info": "i", "error": "!", "question": "?"}.get(kind, "i")
        icon = tk.Label(
            content,
            text=icon_text,
            bg="#2f6f5e" if kind != "error" else "#a33a32",
            fg="#ffffff",
            width=2,
            height=1,
            font=("Segoe UI", 14, "bold"),
        )
        icon.pack(side="left", padx=(0, 14), anchor="n")
        message_label = ttk.Label(content, text=message, wraplength=380, justify="left")
        message_label.pack(side="left", fill="x", expand=True)

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(18, 0))

        def close(value: bool) -> None:
            result["value"] = value
            dialog.destroy()

        if kind == "question":
            ttk.Button(button_row, text="否", command=lambda: close(False), style="Secondary.TButton", width=9).pack(side="right")
            ttk.Button(button_row, text="是", command=lambda: close(True), style="Secondary.TButton", width=9).pack(side="right", padx=(0, 8))
            dialog.bind("<Return>", lambda _event: close(True))
        else:
            ttk.Button(button_row, text="确定", command=lambda: close(True), style="Compact.TButton", width=10).pack(side="right")
            dialog.bind("<Return>", lambda _event: close(True))
        dialog.bind("<Escape>", lambda _event: close(False))

        line_count = message.count("\n") + max(len(message) // 34, 1)
        dialog_height = max(168, min(300, 108 + line_count * 18))
        self.center_window(dialog, 500, dialog_height, parent=target)
        dialog.focus_force()
        self.wait_window(dialog)
        target.lift()
        target.focus_force()
        return result["value"]

    def show_error(self, message: str, parent: tk.Toplevel | None = None) -> None:
        self.show_custom_dialog(message, kind="error", parent=parent)

    def show_info(self, message: str, parent: tk.Toplevel | None = None) -> None:
        self.show_custom_dialog(message, kind="info", parent=parent)

    def ask_yes_no(self, message: str, parent: tk.Toplevel | None = None) -> bool:
        return self.show_custom_dialog(message, kind="question", parent=parent)

    def show_about_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"关于 {APP_NAME}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg="#f3f4f7")

        container = ttk.Frame(dialog, padding=(28, 16))
        container.pack(fill="both", expand=True)

        if self.about_mark_image is not None:
            tk.Label(container, image=self.about_mark_image, bg="#f3f4f7", borderwidth=0).pack(pady=(0, 7))
        else:
            about_mark = tk.Canvas(container, width=64, height=64, bg="#f3f4f7", highlightthickness=0)
            self._draw_app_mark(about_mark, "#111111")
            about_mark.pack(pady=(0, 7))
        ttk.Label(container, text=APP_NAME, style="Title.TLabel").pack(pady=(0, 3))
        details_row = ttk.Frame(container)
        details_row.pack(pady=(0, 9))
        ttk.Label(details_row, text=f"版本 {APP_VERSION}", style="Hint.TLabel").pack(side="left", padx=(0, 24))
        ttk.Label(details_row, text=f"作者：{AUTHOR_NAME}", style="Hint.TLabel").pack(side="left")
        ttk.Label(
            container,
            text="安全修改 Codex 本地配置的 Windows 桌面工具",
            justify="center",
            wraplength=500,
        ).pack(pady=(0, 8))

        email_label = tk.Label(
            container,
            text=f"联系邮箱：{CONTACT_EMAIL}",
            bg="#f3f4f7",
            fg="#2f6f5e",
            activeforeground="#285f51",
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        email_label.pack(pady=(0, 5))
        def copy_email(_event=None) -> None:
            self.clipboard_clear()
            self.clipboard_append(CONTACT_EMAIL)
            self.update_idletasks()
            original_text = email_label.cget("text")
            email_label.configure(text="邮箱已复制")
            dialog.after(1800, lambda: email_label.winfo_exists() and email_label.configure(text=original_text))

        email_label.bind("<Button-1>", copy_email)
        project_label = tk.Label(
            container,
            text=f"项目地址：{PROJECT_URL}",
            bg="#f3f4f7",
            fg="#2f6f5e",
            activeforeground="#285f51",
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        project_label.pack(pady=(0, 7))

        def open_project(_event=None) -> None:
            webbrowser.open_new_tab(PROJECT_URL)

        project_label.bind("<Button-1>", open_project)
        available_update = self._available_update
        if available_update is None:
            update_status_var = tk.StringVar(value="")
            update_button_text = "检查更新"
        else:
            update_status_var = tk.StringVar(value=f"发现新版本 {available_update.version}")
            update_button_text = "前往下载"
        update_button = ttk.Button(
            container,
            text=update_button_text,
            style="Compact.TButton",
            width=10,
        )
        if available_update is None:
            update_button.configure(
                command=lambda: self.start_update_check(
                    manual=True,
                    parent=dialog,
                    status_var=update_status_var,
                    button=update_button,
                )
            )
        else:
            update_button.configure(command=lambda: webbrowser.open_new_tab(available_update.page_url))
        update_button.pack(pady=(1, 5))
        ttk.Label(container, textvariable=update_status_var, style="Hint.TLabel").pack(pady=(0, 5))
        ttk.Label(
            container,
            text=f"Copyright © 2026 {AUTHOR_NAME}",
            style="Hint.TLabel",
        ).pack()

        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.center_window(dialog, 560)
        dialog.focus_force()

    def check_for_updates_on_startup(self) -> None:
        self.start_update_check(manual=False)

    def start_update_check(
        self,
        manual: bool,
        parent: tk.Toplevel | None = None,
        status_var: tk.StringVar | None = None,
        button: ttk.Button | None = None,
    ) -> None:
        if self._update_check_in_progress:
            if status_var is not None:
                status_var.set("正在检查更新...")
            if button is not None:
                button.configure(state="disabled")
            self.after(
                400,
                lambda: self.start_update_check(manual, parent, status_var, button)
                if parent is None or parent.winfo_exists()
                else None,
            )
            return
        self._update_check_in_progress = True
        if status_var is not None:
            status_var.set("正在检查更新...")
        if button is not None:
            button.configure(state="disabled")

        def worker() -> None:
            try:
                update = fetch_latest_release()
                error = None
            except UpdateCheckError as exc:
                update = None
                error = str(exc)
            except Exception:
                update = None
                error = "检查更新时发生未知错误。"
            self.after(
                0,
                lambda: self._finish_update_check(manual, parent, status_var, button, update, error),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check(
        self,
        manual: bool,
        parent: tk.Toplevel | None,
        status_var: tk.StringVar | None,
        button: ttk.Button | None,
        update: UpdateInfo | None,
        error: str | None,
    ) -> None:
        self._update_check_in_progress = False
        try:
            if button is not None and button.winfo_exists():
                button.configure(state="normal")
        except tk.TclError:
            button = None
        if error is not None:
            if manual and status_var is not None:
                status_var.set(error)
            return
        if update is None:
            self._set_available_update(None)
            if manual and status_var is not None:
                status_var.set(f"当前已是最新版本 {APP_VERSION}")
            return
        self._set_available_update(update)
        if status_var is not None:
            status_var.set(f"发现新版本 {update.version}")
        if button is not None:
            button.configure(
                text="前往下载",
                command=lambda: webbrowser.open_new_tab(update.page_url),
            )
    def ask_config_name(
        self,
        config_dir: Path,
        default_name: str,
        description: str,
        parent: tk.Toplevel | None = None,
        rename_path: Path | None = None,
    ) -> str | None:
        target = parent or self
        dialog = tk.Toplevel(target)
        dialog.title("修改配置名称" if rename_path is not None else "保存配置")
        dialog.transient(target)
        dialog.grab_set()
        dialog.resizable(False, False)

        container = ttk.Frame(dialog, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text=description).pack(anchor="w", pady=(0, 8))
        ttk.Label(container, text="配置名称：", style="Hint.TLabel").pack(anchor="w", pady=(0, 4))
        name_var = tk.StringVar(value=default_name)
        entry = ttk.Entry(container, textvariable=name_var, width=52)
        entry.pack(fill="x")
        error_var = tk.StringVar()
        error_label = tk.Label(
            container,
            textvariable=error_var,
            bg="#f3f4f7",
            fg="#c2410c",
            anchor="w",
            justify="left",
            wraplength=390,
            font=("Microsoft YaHei UI", 9),
        )
        error_label.pack(fill="x", pady=(6, 0))

        result = {"value": None}

        def accept() -> None:
            try:
                if rename_path is None:
                    value = validate_new_backup_name(config_dir, name_var.get())
                else:
                    value = validate_backup_name_format(name_var.get())
                    if named_backup_records(config_dir, value, exclude_path=rename_path):
                        raise BackupNameConflictError("已存在同名配置，请使用新的配置名称。")
            except BackupNameError as exc:
                error_var.set(str(exc))
                entry.focus_set()
                return
            result["value"] = value
            dialog.destroy()

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(16, 0))
        ttk.Button(button_row, text="取消", command=dialog.destroy, style="Compact.TButton", width=9).pack(side="right")
        ttk.Button(button_row, text="确定", command=accept, style="Compact.TButton", width=9).pack(side="right", padx=(0, 8))

        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        if rename_path is None:
            try:
                validate_new_backup_name(config_dir, default_name)
            except BackupNameError as exc:
                error_var.set(str(exc))
        self.center_window(dialog, 440, 205, parent=target)
        entry.focus_set()
        entry.selection_range(0, "end")
        self.wait_window(dialog)
        return result["value"]

    def profile_result_message(self, result: BackupResult) -> str:
        if result.record is None:
            return "配置已保存。"
        action = "已新增配置" if result.status == "created" else "已使用已有配置"
        return f"{action}：{result.record.name}"

    def _load_initial_path(self) -> None:
        settings = load_settings()
        possible = []
        saved = settings.get("config_dir")
        if saved:
            possible.append(Path(saved))
        possible.extend(candidate_config_dirs())
        for path in possible:
            if is_codex_config_dir(path) or is_official_login_mode(path):
                self.path_var.set(str(path))
                self.load_path(path)
                return
        default_path = Path.home() / ".codex"
        self.path_var.set(str(default_path))
        self.load_path(default_path)

    def current_path(self) -> Path:
        return canonical_config_path(Path(self.path_var.get()))

    def choose_path(self) -> None:
        selected = filedialog.askdirectory(
            parent=self,
            title="选择 Codex 配置目录",
            initialdir=str(self.current_path().parent if self.current_path().parent.exists() else Path.home()),
        )
        if selected:
            self.path_var.set(selected)
            self.load_path(Path(selected))

    def scan_paths(self) -> None:
        self._notify("正在扫描常见位置...")
        self.update_idletasks()

        def worker() -> None:
            found = scan_common_locations()
            self.after(0, lambda: self._finish_scan(found))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_scan(self, found: list[Path]) -> None:
        if not found:
            self._notify("没有扫描到配置目录，可以点击“浏览...”手动选择。")
            return
        if len(found) == 1:
            self.path_var.set(str(found[0]))
            self.load_path(found[0])
            return
        picker = tk.Toplevel(self)
        picker.title("选择扫描结果")
        picker.transient(self)
        picker.grab_set()
        ttk.Label(picker, text="扫描到多个可能的 Codex 配置目录，请选择一个：").pack(anchor="w", padx=16, pady=(16, 8))
        listbox = tk.Listbox(picker, height=8, font=("Consolas", 10))
        listbox.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for item in found:
            listbox.insert("end", str(item))
        listbox.selection_set(0)

        def accept() -> None:
            selection = listbox.curselection()
            if selection:
                path = Path(listbox.get(selection[0]))
                self.path_var.set(str(path))
                self.load_path(path)
            picker.destroy()

        ttk.Button(picker, text="使用选中目录", command=accept, style="Compact.TButton", width=14).pack(anchor="e", padx=16, pady=(0, 16))
        self.center_window(picker, 560, 300)

    def load_path(self, path: Path) -> None:
        path = canonical_config_path(path)
        self.path_var.set(str(path))
        template_created = False
        template_pending = False
        first_use = not (path / "auth.json").exists() and not (path / "config.toml").exists()
        state, issues = classify_config_for_editing(path)
        official_login_mode = is_official_login_mode(path)

        if state == "editable" and official_login_mode:
            set_official_login_mode(path, False)
            official_login_mode = False

        if state == "needs_template" and not official_login_mode:
            if first_use:
                try:
                    create_custom_template_config(
                        path,
                        None,
                        TEMPLATE_PROVIDER_NAME,
                        TEMPLATE_BASE_URL,
                        TEMPLATE_MODEL,
                    )
                    template_created = True
                    set_official_login_mode(path, False)
                except OSError as exc:
                    self.show_error(f"自动创建模板失败：\n{exc}")
            else:
                template_pending = True
        elif state == "conflict" and not official_login_mode:
            self.show_error(
                "检测到复杂或冲突配置，软件不会自动覆盖。\n\n"
                + "\n".join(f"- {item}" for item in issues)
            )

        config = read_codex_config(path)
        self.api_key_var.set(config.api_key)
        self.provider_var.set(config.provider or DEFAULT_PROVIDER)
        self.base_url_var.set(config.base_url or DEFAULT_BASE_URL)
        self.model_var.set(config.model or TEMPLATE_MODEL)
        self.model_display_name_var.set(config.model_display_name)
        pending_profile = None if official_login_mode else pending_active_profile_path(path)
        matching_profile = (
            backup_record_from_path(pending_profile)
            if pending_profile is not None
            else (None if official_login_mode else find_matching_backup(path))
        )
        if official_login_mode:
            self.current_config_prefix_var.set("正在使用：")
            self.current_config_name_var.set("官方登录")
            self.current_config_suffix_var.set("")
        elif matching_profile is not None:
            set_active_profile_path(matching_profile.path)
            self.current_config_prefix_var.set("正在使用：")
            self.current_config_name_var.set(matching_profile.name)
            self.current_config_suffix_var.set(" 配置")
        else:
            self.current_config_prefix_var.set("")
            self.current_config_name_var.set("未保存配置")
            self.current_config_suffix_var.set("")
        save_settings(path)
        self._refresh_official_page()
        if hasattr(self, "profile_tree") and self.active_page == "profiles":
            self.refresh_profiles()
        if template_created:
            self._notify(f"检测到首次使用，已创建可编辑配置：{path}")
            return
        if template_pending:
            self._notify("当前配置尚不可直接编辑；填写 API 配置后点击“保存配置”新增命名配置。")
            return
        if official_login_mode:
            if config.config_exists:
                self._notify("已保留 Codex 官方登录配置；可直接打开 Codex 登录 GPT 账号。")
            else:
                self._notify("已进入官方登录模式；请关闭本工具并启动 Codex，按提示登录 GPT 账号。")
            return
        markers = []
        markers.append("auth.json 已找到" if config.auth_exists else "auth.json 不存在")
        markers.append("config.toml 已找到" if config.config_exists else "config.toml 不存在")
        self._notify(f"已读取：{path}（{'，'.join(markers)}）")
    def reload_current(self) -> None:
        self.load_path(self.current_path())

    def toggle_key_visibility(self) -> None:
        visible = not self.show_key_var.get()
        self.show_key_var.set(visible)
        self.key_entry.configure(show="" if visible else "*")
        if hasattr(self, "key_toggle_button"):
            self._draw_eye(self.key_toggle_button, hidden=visible)

    def validate_form(self) -> bool:
        path = self.current_path()
        if not str(path).strip():
            self.show_error("请先选择 Codex 配置目录。")
            return False
        base_url = self.base_url_var.get().strip()
        provider = self.provider_var.get().strip()
        model = self.model_var.get().strip()
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
        state, issues = classify_config_for_editing(path)
        if state == "conflict":
            self.show_error(
                "保存失败：检测到复杂或冲突配置，软件不会自动覆盖。\n\n"
                + "\n".join(f"- {item}" for item in issues)
            )
            return

        api_key = self.api_key_var.get()
        active_provider = self.provider_var.get().strip()
        base_url = self.base_url_var.get()
        model = self.model_var.get()
        model_display_name = ""
        signature = build_requested_signature(path, api_key, active_provider, base_url, model, state)
        existing = find_matching_backup(path, signature)
        config_name = None
        if existing is None:
            config_name = self.ask_config_name(
                path,
                suggested_config_name(active_provider),
                f"新增配置：{active_provider}",
            )
            if config_name is None:
                self._notify("已取消新增配置，当前配置未修改。")
                return

        try:
            result = save_config_profile(
                path,
                api_key,
                active_provider,
                base_url,
                model,
                state,
                config_name,
                model_display_name=model_display_name,
            )
        except (OSError, json.JSONDecodeError, BackupNameError) as exc:
            self.show_error(f"保存失败：\n{exc}")
            return
        set_official_login_mode(path, False)
        if result.record is not None:
            set_active_profile_path(result.record.path)
        result_message = self.profile_result_message(result)
        self.reload_current()
        self._notify(f"保存成功；{result_message}；当前已使用配置：{active_provider}")
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
            restore_default_config(self.current_path())
        except OSError as exc:
            self.show_error(f"恢复失败：\n{exc}")
            return

        set_official_login_mode(self.current_path(), True)
        set_pending_active_profile_path(None)
        self.api_key_var.set("")
        self.provider_var.set(DEFAULT_PROVIDER)
        self.base_url_var.set(DEFAULT_BASE_URL)
        self.model_var.set(TEMPLATE_MODEL)
        self.current_config_name_var.set("官方登录")
        self.current_config_prefix_var.set("正在使用：")
        self.current_config_suffix_var.set("")
        self._refresh_official_page()
        self.refresh_profiles()
        self._notify("已进入官方登录模式，现有会话和配置均已保留。")
        self.show_info("已进入官方登录模式。\n\n聊天记录和已保存的 API 配置均已保留。请关闭本工具并启动 Codex，按提示登录。")

    def show_backup_settings(self) -> None:
        self.show_page("profiles")

    def open_backup_dir(self) -> None:
        backup_dir = self.current_path() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(backup_dir))


def main() -> None:
    mutex_handle = acquire_single_instance()
    if mutex_handle is None:
        show_already_running_message()
        return
    try:
        app = CodexConfigApp()
        app.mainloop()
    finally:
        release_single_instance(mutex_handle)


if __name__ == "__main__":
    main()
