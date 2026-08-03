import json
import os
import re
import shutil
import sys
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk


APP_NAME = "Codex 配置助手"
APP_VERSION = "1.2.0"
AUTHOR_NAME = "k.x"
CONTACT_EMAIL = "1099530893@qq.com"
PROJECT_URL = "https://github.com/z1099530893/Codex_ConfigTool"
DONATION_IMAGE_NAME = "赞赏.png"
APP_ICON_PNG_NAME = "app_icon.png"
APP_ICON_ICO_NAME = "app_icon.ico"
TITLE_ICON_PNG_NAME = "app_icon_title.png"
EYE_ICON_NAME = "eye_smooth.png"
EYE_OFF_ICON_NAME = "eye_off_smooth.png"
ABOUT_MARK_PNG_NAME = "app_icon_about.png"
WINDOW_WIDTH = 820
WINDOW_HEIGHT = 500
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


def resource_path(name: str) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / name


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


class ConfigConflictError(OSError):
    pass


class BackupNameError(ValueError):
    pass


class BackupNameConflictError(BackupNameError):
    pass


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
    settings["config_dir"] = str(config_dir)
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_setting_value(key: str, value: object) -> None:
    settings = load_settings()
    settings[key] = value
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def should_show_onboarding(settings: dict) -> bool:
    if HIDE_ONBOARDING_KEY in settings:
        return False
    return not bool(settings.get(ONBOARDING_SHOWN_KEY, False))


def normalized_path_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve()).lower()
    except OSError:
        return str(path.expanduser()).lower()


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


def append_provider_section(lines: list[str], provider: str, base_url: str) -> list[str]:
    output = list(lines)
    if output and not output[-1].endswith("\n"):
        output[-1] += "\n"
    if output and output[-1].strip():
        output.append("\n")
    output.extend(
        [
            f"[model_providers.{provider}]\n",
            f"name = {quote_toml_string(provider)}\n",
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


def build_backup_signature(config_dir: Path) -> BackupSignature | None:
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
        for file_name in ("auth.json", "config.toml")
    }


def restore_config_files(config_dir: Path, snapshot: dict[str, bytes | None]) -> None:
    for file_name, content in snapshot.items():
        path = config_dir / file_name
        if content is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


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
        for file_name in ("auth.json", "config.toml"):
            source = config_dir / file_name
            if source.exists():
                shutil.copy2(source, backup_dir / file_name)
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
) -> BackupRecord:
    name = validate_new_backup_name(config_dir, name)
    signature = build_requested_signature(
        config_dir,
        api_key,
        provider_name,
        base_url,
        model,
        "needs_template",
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
        create_custom_template_config(
            profile_dir,
            api_key,
            provider_name,
            base_url,
            model,
            persist_settings=False,
        )
        record = backup_record_from_path(profile_dir)
        if apply_to_current:
            restore_backup(config_dir, record.path)
    except (OSError, json.JSONDecodeError):
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
            create_custom_template_config(
                profile_dir,
                api_key,
                provider_name,
                base_url,
                model,
                persist_settings=False,
            )
        else:
            save_codex_config(
                profile_dir,
                api_key,
                provider_name,
                base_url,
                model,
                persist_settings=False,
            )
        if original_record.name != name:
            updated_path = rename_backup(config_dir, profile_dir, name).path
        if apply_to_current:
            restore_backup(config_dir, updated_path)
    except (OSError, json.JSONDecodeError, BackupNameError):
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
    for backup_dir in backup_dirs:
        resolved = validate_backup_path(config_dir, backup_dir)
        if resolved.exists():
            shutil.rmtree(resolved)


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


def restore_backup(config_dir: Path, backup_dir: Path) -> None:
    backup_dir = validate_backup_path(config_dir, backup_dir)
    if not ((backup_dir / "auth.json").exists() or (backup_dir / "config.toml").exists()):
        raise OSError("选择的配置不包含可使用的配置文件。")
    snapshot = capture_config_files(config_dir)
    try:
        for file_name in ("auth.json", "config.toml"):
            source = backup_dir / file_name
            target = config_dir / file_name
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif target.exists():
                target.unlink()
        save_settings(config_dir)
    except OSError:
        restore_config_files(config_dir, snapshot)
        raise


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
    auth_path.write_text(json.dumps(auth_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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

    lines = read_text(config_path).splitlines(keepends=True)
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


def save_codex_config(
    config_dir: Path,
    api_key: str,
    display_name: str,
    base_url: str,
    model: str,
    persist_settings: bool = True,
) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    base_url = base_url.strip() or DEFAULT_BASE_URL

    auth_path = config_dir / "auth.json"
    config_path = config_dir / "config.toml"
    auth_text = read_text(auth_path) if auth_path.exists() else None
    config_lines = read_text(config_path).splitlines(keepends=True) if config_path.exists() else []
    provider_id = get_top_level_value(config_lines, "model_provider") or DEFAULT_PROVIDER
    conflicts = find_config_conflicts(config_lines, provider_id, auth_text)
    if conflicts:
        raise ConfigConflictError(
            "检测到配置里有重复项，或当前配置没有可安全修改的自定义 Provider 段。\n\n"
            + "\n".join(f"- {item}" for item in conflicts)
            + "\n\n普通保存不会修改 model_provider 或重命名 Provider 段，以避免影响 Codex 聊天窗口状态。"
        )

    update_auth_json(auth_path, api_key)
    update_existing_config_toml(config_path, display_name, base_url, model)
    if persist_settings:
        save_settings(config_dir)


def restore_default_config(config_dir: Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    snapshot = capture_config_files(config_dir)
    try:
        for file_name in ("auth.json", "config.toml"):
            path = config_dir / file_name
            if path.exists():
                path.unlink()
        save_settings(config_dir)
    except OSError:
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
    auth_path = config_dir / "auth.json"
    if api_key is None:
        if not auth_path.exists():
            auth_path.write_text("{}\n", encoding="utf-8")
    else:
        update_auth_json(auth_path, api_key)
    write_text(config_dir / "config.toml", build_custom_template_config_toml(provider_name, base_url, model))
    if persist_settings:
        save_settings(config_dir)


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
) -> BackupResult:
    signature = build_requested_signature(config_dir, api_key, provider_name, base_url, model, state)
    existing = find_matching_backup(config_dir, signature)
    if existing is not None:
        snapshot = capture_config_files(config_dir)
        try:
            if state == "needs_template":
                restore_backup(config_dir, existing.path)
            else:
                save_codex_config(config_dir, api_key, provider_name, base_url, model)
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
            create_custom_template_config(config_dir, api_key, provider_name, base_url, model)
        else:
            save_codex_config(config_dir, api_key, provider_name, base_url, model)
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
        self.api_key_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择 Codex 配置目录")
        self.current_config_name_var = tk.StringVar(value="未保存配置")
        self.current_config_prefix_var = tk.StringVar(value="")
        self.current_config_suffix_var = tk.StringVar(value="")
        self.official_status_var = tk.StringVar(value="当前未使用官方登录模式")
        self.profile_search_var = tk.StringVar()
        self.profile_sort_desc = False
        self.pages: dict[str, tk.Frame] = {}
        self.nav_items: dict[str, tuple[tk.Frame, tk.Label, tk.Button]] = {}
        self.active_page = "current"
        self._window_drag: tuple[int, int, int, int] | None = None
        self._window_drag_latest: tuple[int, int] | None = None
        self._window_drag_job: str | None = None
        self._minimized = False
        self.app_icon_image = self._load_ui_image(APP_ICON_PNG_NAME)
        self.title_icon_image = self._load_ui_image(TITLE_ICON_PNG_NAME)
        self.eye_icon = self._load_ui_image(EYE_ICON_NAME)
        self.eye_off_icon = self._load_ui_image(EYE_OFF_ICON_NAME)
        self.about_mark_image = self._load_ui_image(ABOUT_MARK_PNG_NAME)
        if self.app_icon_image is not None:
            self.iconphoto(True, self.app_icon_image)
        try:
            self.iconbitmap(str(resource_path(APP_ICON_ICO_NAME)))
        except (OSError, tk.TclError):
            pass
        self.donation_image = self._load_donation_image()
        if self.donation_image:
            factor = max((self.donation_image.width() + 111) // 112, 1)
            self.donation_thumbnail = self.donation_image.subsample(factor, factor)
            dialog_factor = max((self.donation_image.width() + 359) // 360, 1)
            self.donation_dialog_image = self.donation_image.subsample(dialog_factor, dialog_factor)
        else:
            self.donation_thumbnail = None
            self.donation_dialog_image = None
        self._build_style()
        self._build_ui()
        self._center_main_window()
        self.bind("<Map>", self._restore_custom_frame, add="+")
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

    def _build_ui(self) -> None:
        shell = tk.Frame(self, bg="#f3f4f7", width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        shell.pack(fill="both", expand=True)
        shell.pack_propagate(False)

        title_bar = tk.Frame(shell, bg="#252525", height=38)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        title_left = tk.Frame(title_bar, bg="#252525")
        title_left.pack(side="left", fill="y", padx=(10, 0))
        icon_label = tk.Label(title_left, image=self.title_icon_image, bg="#252525", borderwidth=0)
        icon_label.pack(side="left", padx=(0, 7))
        icon_label.bind("<ButtonPress-1>", self._start_window_move)
        icon_label.bind("<B1-Motion>", self._move_window)
        title_label = tk.Label(
            title_left,
            text=APP_NAME,
            bg="#252525",
            fg="#f4f4f4",
            font=("Microsoft YaHei UI", 9),
        )
        title_label.pack(side="left")

        close_button = self._title_icon_button(title_bar, "close", self.destroy)
        close_button.pack(side="right", fill="y")
        minimize_button = self._title_icon_button(title_bar, "minimize", self._minimize_window)
        minimize_button.pack(side="right", fill="y")
        about_button = self._title_icon_button(title_bar, "about", self.show_about_dialog)
        about_button.pack(side="right", fill="y")
        Tooltip(about_button, "关于软件")
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
            ("guide", "新手引导"),
        ):
            self._create_nav_item(nav, key, text)

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
        canvas = tk.Canvas(parent, width=42, height=38, bg="#252525", highlightthickness=0, cursor="hand2")

        def draw(background: str = "#252525") -> None:
            canvas.configure(bg=background)
            canvas.delete("all")
            color = "#f3f4f6"
            glyph = {"about": "ⓘ", "minimize": "−", "close": "×"}[kind]
            font_size = 12 if kind == "about" else 17
            canvas.create_text(21, 18, text=glyph, fill=color, font=("Segoe UI", font_size))

        hover = "#c42b1c" if kind == "close" else "#3d3d3d"
        canvas.bind("<Enter>", lambda _event: draw(hover))
        canvas.bind("<Leave>", lambda _event: draw())
        canvas.bind("<Button-1>", lambda _event: command())
        draw()
        return canvas

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
        header.pack(fill="x", padx=28, pady=(16, 64))
        title_row = tk.Frame(header, bg="#f3f4f7")
        title_row.pack(fill="x")
        status_dot = tk.Canvas(title_row, width=12, height=22, bg="#f3f4f7", highlightthickness=0)
        status_dot.create_oval(3, 8, 9, 14, fill="#2e9b63", outline="")
        status_dot.pack(side="left", padx=(0, 5))
        status_font = ("Microsoft YaHei UI", 11, "bold")
        tk.Label(title_row, textvariable=self.current_config_prefix_var, bg="#f3f4f7", fg="#20242b", font=status_font, padx=0, borderwidth=0).pack(side="left")
        tk.Label(title_row, textvariable=self.current_config_name_var, bg="#f3f4f7", fg="#20242b", font=status_font, padx=0, borderwidth=0).pack(side="left")
        tk.Label(title_row, textvariable=self.current_config_suffix_var, bg="#f3f4f7", fg="#20242b", font=status_font, padx=0, borderwidth=0).pack(side="left")
        tk.Label(
            header,
            text="欢迎使用 Codex 配置助手，如果觉得软件好用，请扫描左侧二维码，支持作者。",
            bg="#f3f4f7",
            fg="#69707d",
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", pady=(5, 0))

        path_panel = self._panel(page, (12, 9))
        tk.Label(path_panel, text="Codex 配置目录", bg="#ffffff", fg="#2a3038", font=("Microsoft YaHei UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
        path_row = tk.Frame(path_panel, bg="#ffffff")
        path_row.pack(fill="x")
        ttk.Entry(path_row, textvariable=self.path_var, state="readonly", style="Readonly.TEntry").pack(side="left", fill="x", expand=True, ipady=1)
        ttk.Button(path_row, text="浏览...", command=self.choose_path, style="Secondary.TButton", width=10).pack(side="left", padx=(8, 0), ipady=1)
        ttk.Button(path_row, text="新增配置", command=self._show_profile_editor, style="Secondary.TButton", width=11).pack(side="left", padx=(8, 0), ipady=1)

        details = self._panel(page, (16, 8))
        details.columnconfigure(1, weight=1)
        self.key_entry = self._readonly_field(details, 0, "API Key", self.api_key_var, secret=True)
        self._readonly_field(details, 1, "Provider 显示名称", self.provider_var)
        self._readonly_field(details, 2, "Base URL", self.base_url_var)
        self._readonly_field(details, 3, "Model", self.model_var)

    def _readonly_field(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar, secret: bool = False) -> ttk.Entry:
        tk.Label(parent, text=label, bg="#ffffff", fg="#303640", font=("Microsoft YaHei UI", 9)).grid(row=row, column=0, sticky="w", padx=(0, 18), pady=6)
        field = tk.Frame(parent, bg="#ffffff")
        field.grid(row=row, column=1, sticky="ew", pady=6)
        entry = ttk.Entry(field, textvariable=variable, state="readonly", show="*" if secret else "", style="Readonly.TEntry")
        entry.pack(side="left", fill="both", expand=True, ipady=1)
        if secret:
            self.key_toggle_button = self._eye_button(field, self.toggle_key_visibility, "#f7f8f9")
            self.key_toggle_button.place(relx=1.0, rely=0.5, anchor="e", x=-2, y=0)
        return entry

    def _build_official_page(self) -> None:
        page = self._new_page("official")
        self._page_header(page, "官方登录", "恢复 Codex 官方登录配置，用自己的 ChatGPT/GPT 账号登录。")
        panel = self._panel(page, (20, 18))
        tk.Label(panel, textvariable=self.official_status_var, bg="#ffffff", fg="#20242b", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w")
        tk.Label(
            panel,
            text=(
                "执行后会删除当前目录中的 auth.json 和 config.toml，由 Codex 在下次启动时重新生成。\n"
                "聊天记录、本地数据库、日志和配置库中的已保存配置不会被删除。"
            ),
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
        sections = (
            ("新增配置", ("打开“新增配置”，填写配置名称、API Key、Provider 显示名称、Base URL 和 Model。", "点击“保存配置”仅保存配置；点击“保存并使用”会立即切换，并需要重启 Codex。")),
            ("切换配置", ("打开“切换配置”，选择已保存的配置并点击“切换到该配置”。", "切换完成后请关闭本工具并重新启动 Codex，使新配置生效。")),
        )
        for title, messages in sections:
            tk.Label(panel, text=title, bg="#ffffff", fg="#20242b", anchor="w", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
            for message in messages:
                tk.Label(panel, text="• " + message, bg="#ffffff", fg="#4f5865", justify="left", anchor="w", wraplength=500, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(0, 7))
            tk.Frame(panel, bg="#eef0f2", height=1).pack(fill="x", pady=(3, 14))

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
        self.overrideredirect(False)
        self.iconify()

    def _restore_custom_frame(self, _event=None) -> None:
        if self._minimized and self.state() == "normal":
            self._minimized = False
            self.after_idle(lambda: (self.overrideredirect(True), self._set_appwindow_style()))

    def _set_appwindow_style(self) -> None:
        if os.name != "nt" or not self.winfo_exists():
            return
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            extended_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            extended_style = (extended_style & ~0x00000080) | 0x00040000
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, extended_style)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except (AttributeError, OSError):
            pass

    def _build_profiles_page(self) -> None:
        page = self._new_page("profiles")
        self._page_header(page, "已保存配置", "按配置名称或 Base URL 查找，并切换、编辑或删除配置。")

        toolbar = tk.Frame(page, bg="#f3f4f7")
        toolbar.pack(fill="x", padx=28, pady=(0, 10))
        ttk.Button(toolbar, text="打开配置库目录", command=self.open_backup_dir, style="Secondary.TButton").pack(side="left", ipady=1)
        ttk.Button(toolbar, text="新增配置", command=self._show_profile_editor, style="Secondary.TButton").pack(side="left", padx=(8, 0), ipady=1)
        self.profile_switch_button = ttk.Button(
            toolbar,
            text="切换到该配置",
            command=self._switch_selected_profile,
            style="Primary.TButton",
        )
        self.profile_switch_button.pack(side="right")
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
        tree_panel.pack(fill="both", expand=True, padx=28, pady=(0, 28))
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
            config = read_codex_config(record.path)
            if query and query not in record.name.casefold() and query not in config.base_url.casefold():
                continue
            item = f"profile-{index}"
            record_key = normalized_path_key(record.path)
            display_name = f"●  {record.name}" if record_key == active_key else record.name
            self.profile_records_by_item[item] = record
            self.profile_tree.insert(
                "",
                "end",
                iid=item,
                values=(display_name, config.base_url),
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
        if len(records) != 1 or self.profile_multi_mode:
            return
        selected = records[0]
        try:
            restore_backup(self.current_path(), selected.path)
        except OSError as exc:
            self.show_error(f"切换配置失败：\n{exc}")
            return
        set_official_login_mode(self.current_path(), False)
        self.load_path(self.current_path())
        self.refresh_profiles(selected.path)
        self._notify(f"已切换到配置：{selected.name}；请重新启动 Codex。")

    def _profile_double_click(self, event) -> str:
        item = self.profile_tree.identify_row(event.y)
        if not item or item not in self.profile_records_by_item or self.profile_multi_mode:
            return "break"
        column = self.profile_tree.identify_column(event.x)
        if self._profile_click_hits_text(item, column, event.x):
            return "break"
        self.profile_tree.selection_set(item)
        self.profile_tree.focus(item)
        self._switch_selected_profile()
        return "break"

    def _profile_click_hits_text(self, item: str, column: str, x: int) -> bool:
        if column not in {"#1", "#2"}:
            return False
        values = self.profile_tree.item(item, "values")
        index = int(column[1:]) - 1
        if index >= len(values):
            return False
        cell = self.profile_tree.bbox(item, column)
        if not cell:
            return False
        font_spec = ttk.Style().lookup("Treeview", "font") or ("Microsoft YaHei UI", 9)
        text_width = tkfont.Font(font=font_spec).measure(str(values[index]))
        text_start = cell[0] + 6
        return text_start <= x <= text_start + text_width + 4

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
        self.load_path(self.current_path())
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
        active_record = find_matching_backup(config_dir)
        editing_active = (
            record is not None
            and active_record is not None
            and normalized_path_key(record.path) == normalized_path_key(active_record.path)
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
        subtitle = "修改后将同步更新当前正在使用的配置。" if editing_active else "保存到配置库，或保存后立即切换使用。"
        tk.Label(container, text=title, bg="#f3f4f7", fg="#171a20", font=("Microsoft YaHei UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        tk.Label(container, text=subtitle, bg="#f3f4f7", fg="#69707d", font=("Microsoft YaHei UI", 8)).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 12))

        name_var = tk.StringVar(value=record.name if record is not None else suggested_config_name(source.provider))
        api_key_var = tk.StringVar(value=source.api_key)
        provider_var = tk.StringVar(value=source.provider or TEMPLATE_PROVIDER_NAME)
        base_url_var = tk.StringVar(value=source.base_url or TEMPLATE_BASE_URL)
        model_var = tk.StringVar(value=source.model or TEMPLATE_MODEL)
        editor_show_key = tk.BooleanVar(value=False)

        def add_row(row: int, label: str, variable: tk.StringVar, secret: bool = False) -> ttk.Entry:
            tk.Label(container, text=label, bg="#f3f4f7", fg="#303640", font=("Microsoft YaHei UI", 9)).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=6)
            field = tk.Frame(container, bg="#f3f4f7")
            field.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)
            entry = ttk.Entry(field, textvariable=variable, show="*" if secret else "", width=48)
            entry.pack(fill="both", expand=True, ipady=1)
            if secret:
                eye_button = self._eye_button(field, lambda: None, "#ffffff")
                eye_button.place(relx=1.0, rely=0.5, anchor="e", x=-2, y=0)

                def toggle() -> None:
                    visible = not editor_show_key.get()
                    editor_show_key.set(visible)
                    entry.configure(show="" if visible else "*")
                    self._draw_eye(eye_button, hidden=visible)

                eye_button.bind("<Button-1>", lambda _event: toggle())
            return entry

        name_entry = add_row(2, "配置名称", name_var)
        add_row(3, "API Key", api_key_var, secret=True)
        add_row(4, "Provider 显示名称", provider_var)
        add_row(5, "Base URL", base_url_var)
        add_row(6, "Model", model_var)
        container.columnconfigure(1, weight=1)

        error_var = tk.StringVar()
        tk.Label(
            container,
            textvariable=error_var,
            bg="#f3f4f7",
            fg="#a33a32",
            anchor="w",
            justify="left",
            font=("Microsoft YaHei UI", 8),
        ).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(5, 0))

        def save(apply_to_current: bool) -> None:
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
                        apply_to_current=apply_to_current,
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
                        apply_to_current=apply_to_current or editing_active,
                    )
            except (OSError, json.JSONDecodeError, BackupNameError) as exc:
                error_var.set(str(exc))
                return

            applied = apply_to_current or editing_active
            if applied:
                set_official_login_mode(config_dir, False)
                self.load_path(config_dir)
            self.refresh_profiles(saved.path)
            dialog.destroy()
            action = "已保存并使用" if applied else "已保存"
            self._notify(f"{action}配置：{saved.name}")
            suffix = "\n\n请关闭本工具并重新启动 Codex。" if applied else ""
            self.show_info(f"{action}“{saved.name}”。{suffix}")

        button_row = tk.Frame(container, bg="#f3f4f7")
        button_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(button_row, text="取消", command=dialog.destroy, style="Compact.TButton", width=9).pack(side="right")
        if editing_active:
            ttk.Button(button_row, text="保存并应用", command=lambda: save(True), style="Primary.TButton", width=12).pack(side="right", padx=(0, 8))
        else:
            ttk.Button(button_row, text="保存并使用", command=lambda: save(True), style="Primary.TButton", width=12).pack(side="right", padx=(0, 8))
            ttk.Button(
                button_row,
                text="保存修改" if record is not None else "保存配置",
                command=lambda: save(False),
                style="Compact.TButton",
                width=11,
            ).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.center_window(dialog, 570, 410)
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
        y = self.winfo_rooty() + self.winfo_height() - toast.winfo_height() - 5
        toast.geometry(f"+{x}+{y}")
        toast.after(duration, lambda: toast.winfo_exists() and toast.destroy())

    def _load_donation_image(self) -> tk.PhotoImage | None:
        try:
            return tk.PhotoImage(file=str(resource_path(DONATION_IMAGE_NAME)))
        except (OSError, tk.TclError):
            return None

    def show_donation_dialog(self) -> None:
        if self.donation_image is None:
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
        dialog.title("新手引导")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg="#f3f4f7")

        container = ttk.Frame(dialog, padding=24)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="欢迎使用 Codex 配置助手", style="Title.TLabel").pack(anchor="w")
        ttk.Label(container, text="新增配置", style="Panel.TLabel", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(12, 5))
        ttk.Label(container, text="打开“新增配置”，填写配置名称和服务商提供的 API 信息。保存并使用后，请关闭本工具并重新启动 Codex。", justify="left", wraplength=430).pack(anchor="w")
        ttk.Label(container, text="切换配置", style="Panel.TLabel", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(16, 5))
        ttk.Label(container, text="打开“切换配置”，选择已保存的配置并切换；切换完成后同样需要重新启动 Codex。", justify="left", wraplength=430).pack(anchor="w")

        def close() -> None:
            save_setting_value(ONBOARDING_SHOWN_KEY, True)
            dialog.destroy()
            self.lift()
            self.focus_force()

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Return>", lambda _event: close())
        dialog.bind("<Escape>", lambda _event: close())
        self.center_window(dialog, 520)
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
        ttk.Label(
            container,
            text=f"Copyright © 2026 {AUTHOR_NAME}",
            style="Hint.TLabel",
        ).pack()

        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.center_window(dialog, 560)
        dialog.focus_force()
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
        return Path(self.path_var.get()).expanduser()

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
        matching_profile = None if official_login_mode else find_matching_backup(path)
        if official_login_mode:
            self.current_config_prefix_var.set("正在使用：")
            self.current_config_name_var.set("官方登录")
            self.current_config_suffix_var.set("")
        elif matching_profile is not None:
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
            )
        except (OSError, json.JSONDecodeError, BackupNameError) as exc:
            self.show_error(f"保存失败：\n{exc}")
            return
        set_official_login_mode(path, False)
        result_message = self.profile_result_message(result)
        self.reload_current()
        self._notify(f"保存成功；{result_message}；当前已使用配置：{active_provider}")
        self.show_info(
            f"配置保存成功。\n\n{result_message}\n"
            f"当前已使用配置：{active_provider}\n"
            "重新打开 Codex 后通常会读取新配置。"
        )

    def restore_defaults(self) -> None:
        message = "是否确认恢复到默认配置？\n\n恢复后请关闭本工具并启动 Codex，按提示登录。"
        if not self.ask_yes_no(message):
            return
        try:
            restore_default_config(self.current_path())
        except OSError as exc:
            self.show_error(f"恢复失败：\n{exc}")
            return

        set_official_login_mode(self.current_path(), True)
        self.api_key_var.set("")
        self.provider_var.set(DEFAULT_PROVIDER)
        self.base_url_var.set(DEFAULT_BASE_URL)
        self.model_var.set(TEMPLATE_MODEL)
        self.current_config_name_var.set("官方登录")
        self.current_config_prefix_var.set("正在使用：")
        self.current_config_suffix_var.set("")
        self._refresh_official_page()
        self.refresh_profiles()
        self._notify("已进入官方登录模式。")
        self.show_info("已恢复默认配置。\n\n请关闭本工具并启动 Codex，按提示登录。")

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
