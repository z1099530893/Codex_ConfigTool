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
from tkinter import filedialog, ttk


APP_NAME = "Codex 配置助手"
APP_VERSION = "1.1.0"
AUTHOR_NAME = "k.x"
CONTACT_EMAIL = "1099530893@qq.com"
PROJECT_URL = "https://github.com/z1099530893/Codex_ConfigTool"
DONATION_IMAGE_NAME = "赞赏.png"
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


def resource_path(name: str) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / name


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
        raise BackupNameError("备份名称不能为空。")
    if len(name) > MAX_BACKUP_NAME_LENGTH:
        raise BackupNameError(f"备份名称不能超过 {MAX_BACKUP_NAME_LENGTH} 个字符。")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise BackupNameError('备份名称不能包含 < > : " / \\ | ? * 等字符。')
    if name in {".", ".."} or name.endswith("."):
        raise BackupNameError("备份名称不能是点号，也不能以点号结尾。")
    return name


def suggested_backup_name(config_dir: Path) -> str:
    provider_name = read_codex_config(config_dir).provider.strip() or DEFAULT_PROVIDER
    suggestion = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", provider_name).strip(". ")
    return suggestion[:MAX_BACKUP_NAME_LENGTH] or "backup"


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


def find_reusable_backup(config_dir: Path, name: str, signature: BackupSignature | None = None) -> BackupRecord | None:
    signature = signature if signature is not None else build_backup_signature(config_dir)
    if signature is None:
        return None
    for record in named_backup_records(config_dir, name):
        if build_backup_signature(record.path) == signature:
            return record
    return None


def validate_new_backup_name(config_dir: Path, name: str, signature: BackupSignature | None = None) -> str:
    name = validate_backup_name_format(name)
    matching_names = named_backup_records(config_dir, name)
    if not matching_names:
        return name
    signature = signature if signature is not None else build_backup_signature(config_dir)
    if signature is not None and any(build_backup_signature(record.path) == signature for record in matching_names):
        return name
    raise BackupNameConflictError("已存在同名备份，但核心配置不同，请使用新的备份名称。")


def create_or_reuse_backup(config_dir: Path, name: str | None) -> BackupResult:
    has_source = any((config_dir / file_name).exists() for file_name in ("auth.json", "config.toml"))
    if not has_source:
        return BackupResult(status="not_needed")
    if name is None:
        raise BackupNameError("当前配置必须先命名备份，才能继续操作。")

    signature = build_backup_signature(config_dir)
    name = validate_new_backup_name(config_dir, name, signature)
    reusable = find_reusable_backup(config_dir, name, signature)
    if reusable is not None:
        return BackupResult(status="reused", record=reusable)

    backup_root = config_dir / "backups"
    timestamp = datetime.now().strftime(BACKUP_TIMESTAMP_FORMAT)
    backup_dir = backup_root / f"{timestamp}-{name}"
    if backup_dir.exists():
        raise BackupNameConflictError("同一秒内已存在同名备份，请稍后重试或使用新的名称。")
    backup_dir.mkdir(parents=True, exist_ok=False)
    for file_name in ("auth.json", "config.toml"):
        source = config_dir / file_name
        if source.exists():
            shutil.copy2(source, backup_dir / file_name)
    return BackupResult(status="created", record=backup_record_from_path(backup_dir))


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
        raise BackupNameConflictError("已存在同名备份，请使用新的备份名称。")
    if record.name == new_name:
        return record

    match = BACKUP_DIR_PATTERN.match(backup_dir.name)
    timestamp = match.group("timestamp") if match else record.created_at.strftime(BACKUP_TIMESTAMP_FORMAT)
    target = backup_dir.parent / f"{timestamp}-{new_name}"
    if target.exists() and normalized_path_key(target) != normalized_path_key(backup_dir):
        raise BackupNameConflictError("目标备份目录已存在，请使用新的备份名称。")
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


def restore_backup(config_dir: Path, backup_dir: Path, backup_name: str | None) -> BackupResult:
    backup_dir = validate_backup_path(config_dir, backup_dir)
    if not ((backup_dir / "auth.json").exists() or (backup_dir / "config.toml").exists()):
        raise OSError("选择的备份不包含可恢复的配置文件。")
    backup_result = create_or_reuse_backup(config_dir, backup_name)
    for file_name in ("auth.json", "config.toml"):
        source = backup_dir / file_name
        target = config_dir / file_name
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
    save_settings(config_dir)
    return backup_result


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
    backup_name: str | None,
) -> BackupResult:
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

    backup_result = create_or_reuse_backup(config_dir, backup_name)
    update_auth_json(auth_path, api_key)
    update_existing_config_toml(config_path, display_name, base_url, model)
    save_settings(config_dir)
    return backup_result


def save_fresh_codex_config(
    config_dir: Path,
    api_key: str,
    provider: str,
    base_url: str,
    backup_name: str | None,
) -> BackupResult:
    config_dir.mkdir(parents=True, exist_ok=True)
    backup_result = create_or_reuse_backup(config_dir, backup_name)
    auth_path = config_dir / "auth.json"
    auth_data = {}
    if api_key.strip():
        auth_data["OPENAI_API_KEY"] = api_key.strip()
    auth_path.write_text(json.dumps(auth_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    config_path = config_dir / "config.toml"
    write_text(config_path, build_fresh_config_toml(api_key, provider, base_url))
    save_settings(config_dir)
    return backup_result


def restore_default_config(config_dir: Path, backup_name: str | None) -> BackupResult:
    config_dir.mkdir(parents=True, exist_ok=True)
    backup_result = create_or_reuse_backup(config_dir, backup_name)
    for file_name in ("auth.json", "config.toml"):
        path = config_dir / file_name
        if path.exists():
            path.unlink()
    save_settings(config_dir)
    return backup_result


def create_custom_template_config(
    config_dir: Path,
    api_key: str | None,
    provider_name: str,
    base_url: str,
    model: str,
    backup_name: str | None,
) -> BackupResult:
    config_dir.mkdir(parents=True, exist_ok=True)
    backup_result = create_or_reuse_backup(config_dir, backup_name)
    auth_path = config_dir / "auth.json"
    if api_key is None:
        if not auth_path.exists():
            auth_path.write_text("{}\n", encoding="utf-8")
    else:
        update_auth_json(auth_path, api_key)
    write_text(config_dir / "config.toml", build_custom_template_config_toml(provider_name, base_url, model))
    save_settings(config_dir)
    return backup_result

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
        self.geometry("860x620")
        self.minsize(760, 570)
        self.configure(bg="#f6f7fb")
        self.path_var = tk.StringVar()
        self.provider_var = tk.StringVar(value=DEFAULT_PROVIDER)
        self.base_url_var = tk.StringVar(value=DEFAULT_BASE_URL)
        self.model_var = tk.StringVar(value=TEMPLATE_MODEL)
        self.api_key_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择或扫描 Codex 配置目录")
        self.donation_image = self._load_donation_image()
        self.donation_thumbnail = self.donation_image.subsample(5, 5) if self.donation_image else None
        self._build_style()
        self._build_ui()
        self._load_initial_path()
        self.after(150, self.show_onboarding_dialog)

    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f6f7fb")
        style.configure("Panel.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f6f7fb", foreground="#1d2433", font=("Microsoft YaHei UI", 10))
        style.configure("Panel.TLabel", background="#ffffff", foreground="#1d2433", font=("Microsoft YaHei UI", 10))
        style.configure("Title.TLabel", background="#f6f7fb", foreground="#111827", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Hint.TLabel", background="#f6f7fb", foreground="#5b6575", font=("Microsoft YaHei UI", 9))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 7))
        style.configure("Compact.TButton", font=("Microsoft YaHei UI", 9), padding=(8, 4))
        style.configure("TEntry", padding=7)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=22)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 14))
        header_left = ttk.Frame(header)
        header_left.pack(side="left", fill="x", expand=True, anchor="n")

        title_button = tk.Button(
            header_left,
            text=f"{APP_NAME}  ⓘ",
            command=self.show_about_dialog,
            bg="#f6f7fb",
            fg="#111827",
            activebackground="#eef2f7",
            activeforeground="#1f6fa9",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 18, "bold"),
            padx=0,
            pady=0,
        )
        title_button.pack(anchor="w")
        ttk.Label(header_left, text="打开后会读取当前 Codex 配置，直接修改需要的字段并保存即可。", style="Hint.TLabel").pack(anchor="w", pady=(4, 2))
        ttk.Label(header_left, text="如果你觉得工具好用，请赞助作者", style="Hint.TLabel").pack(anchor="w")

        if self.donation_thumbnail is not None:
            donation_button = tk.Button(
                header,
                image=self.donation_thumbnail,
                command=self.show_donation_dialog,
                bg="#f6f7fb",
                activebackground="#eef2f7",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                cursor="hand2",
                padx=0,
                pady=0,
            )
            donation_button.pack(side="right", anchor="n", padx=(16, 0))

        path_frame = ttk.Frame(root, style="Panel.TFrame", padding=18)
        path_frame.pack(fill="x", pady=(0, 14))
        ttk.Label(path_frame, text="Codex 配置目录", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var)
        path_entry.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        ttk.Button(path_frame, text="浏览...", command=self.choose_path).grid(row=1, column=1, sticky="nsew", padx=(0, 8))
        ttk.Button(path_frame, text="扫描", command=self.scan_paths).grid(row=1, column=2, sticky="nsew")
        path_frame.columnconfigure(0, weight=1)

        form = ttk.Frame(root, style="Panel.TFrame", padding=18)
        form.pack(fill="both", expand=True, pady=(0, 14))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="API Key", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=8)
        self.key_entry = ttk.Entry(form, textvariable=self.api_key_var, show="*")
        self.key_entry.grid(row=0, column=1, sticky="ew", pady=8)
        ttk.Checkbutton(form, text="显示", variable=self.show_key_var, command=self.toggle_key_visibility).grid(row=0, column=2, padx=(10, 0), sticky="w")

        ttk.Label(form, text="Provider 显示名称", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.provider_var).grid(row=1, column=1, sticky="ew", pady=8)

        ttk.Label(form, text="Base URL", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.base_url_var).grid(row=2, column=1, sticky="ew", pady=8)

        ttk.Label(form, text="Model", style="Panel.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Entry(form, textvariable=self.model_var).grid(row=3, column=1, sticky="ew", pady=8)

        actions = ttk.Frame(root)
        actions.pack(fill="x")
        for text, command in (
            ("重新读取", self.reload_current),
            ("备份设置", self.show_backup_settings),
            ("打开备份目录", self.open_backup_dir),
            ("恢复默认配置", self.restore_defaults),
            ("新手引导", lambda: self.show_onboarding_dialog(force=True)),
        ):
            ttk.Button(actions, text=text, command=command, style="Compact.TButton", width=13).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="保存配置", command=self.save_current, style="Compact.TButton", width=13).pack(side="right")

        status_frame = ttk.Frame(root, height=38)
        status_frame.pack(fill="x", pady=(10, 0))
        status_frame.pack_propagate(False)
        status = ttk.Label(status_frame, textvariable=self.status_var, style="Hint.TLabel", justify="left")
        status.pack(anchor="w", fill="x")
        status_frame.bind("<Configure>", lambda event: status.configure(wraplength=max(event.width - 4, 120)))

    def center_window(self, window: tk.Toplevel, width: int | None = None, height: int | None = None, parent: tk.Misc | None = None) -> None:
        parent_window = (parent or self).winfo_toplevel()
        parent_window.update_idletasks()
        window.update_idletasks()
        if width is None:
            width = window.winfo_reqwidth()
        if height is None:
            height = window.winfo_reqheight()
        frame_offset_x = window.winfo_rootx() - window.winfo_x()
        frame_offset_y = window.winfo_rooty() - window.winfo_y()
        parent_x = parent_window.winfo_rootx()
        parent_y = parent_window.winfo_rooty()
        parent_width = parent_window.winfo_width()
        parent_height = parent_window.winfo_height()
        x = parent_x + max((parent_width - width) // 2, 0) - frame_offset_x
        y = parent_y + max((parent_height - height) // 2, 0) - frame_offset_y
        window.geometry(f"{width}x{height}+{x}+{y}")

    def focus_for_dialog(self) -> None:
        self.update_idletasks()
        self.lift()
        self.focus_force()

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
        dialog.configure(bg="#f6f7fb")

        container = ttk.Frame(dialog, padding=20)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="感谢你的支持", style="Title.TLabel").pack(pady=(0, 12))
        tk.Label(
            container,
            image=self.donation_image,
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
        dialog.configure(bg="#f6f7fb")

        container = ttk.Frame(dialog, padding=24)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="欢迎使用 Codex 配置助手", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="按照下面三步完成配置：",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(5, 16))

        steps = (
            ("1", "填写服务商提供的 API Key、Base URL 和 Model。\nProvider 显示名称填写服务商名称。"),
            ("2", "点击“保存配置”。保存前，请为当前配置命名备份。"),
            ("3", "完全退出并重新打开 Codex，使新配置生效。"),
        )
        for number, message in steps:
            row = ttk.Frame(container)
            row.pack(fill="x", pady=(0, 13))
            tk.Label(
                row,
                text=number,
                bg="#1f7ed0",
                fg="#ffffff",
                width=2,
                height=1,
                font=("Microsoft YaHei UI", 10, "bold"),
            ).pack(side="left", anchor="n", padx=(0, 12))
            ttk.Label(
                row,
                text=message,
                justify="left",
                wraplength=405,
            ).pack(side="left", fill="x", expand=True)

        ttk.Label(
            container,
            text="如果输入框已经显示内容，直接修改需要的项目即可。",
            style="Hint.TLabel",
        ).pack(anchor="w")

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
            bg="#1f7ed0" if kind != "error" else "#c2410c",
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
            ttk.Button(button_row, text="否", command=lambda: close(False), style="Compact.TButton", width=9).pack(side="right")
            ttk.Button(button_row, text="是", command=lambda: close(True), style="Compact.TButton", width=9).pack(side="right", padx=(0, 8))
            dialog.bind("<Return>", lambda _event: close(True))
        else:
            ttk.Button(button_row, text="确定", command=lambda: close(True), style="Compact.TButton", width=10).pack(side="right")
            dialog.bind("<Return>", lambda _event: close(True))
        dialog.bind("<Escape>", lambda _event: close(False))

        line_count = message.count("\n") + max(len(message) // 34, 1)
        dialog_height = max(180, min(340, 130 + line_count * 18))
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
        dialog.configure(bg="#f6f7fb")

        container = ttk.Frame(dialog, padding=(28, 16))
        container.pack(fill="both", expand=True)

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
            bg="#f6f7fb",
            fg="#1f6fa9",
            activeforeground="#145a86",
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
            bg="#f6f7fb",
            fg="#1f6fa9",
            activeforeground="#145a86",
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
    def ask_backup_name(
        self,
        config_dir: Path,
        default_name: str,
        description: str,
        parent: tk.Toplevel | None = None,
        rename_path: Path | None = None,
    ) -> str | None:
        target = parent or self
        source_signature = build_backup_signature(config_dir)
        dialog = tk.Toplevel(target)
        dialog.title("备份名称")
        dialog.transient(target)
        dialog.grab_set()
        dialog.resizable(False, False)

        container = ttk.Frame(dialog, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text=description).pack(anchor="w", pady=(0, 8))
        ttk.Label(container, text="备份名称：", style="Hint.TLabel").pack(anchor="w", pady=(0, 4))
        name_var = tk.StringVar(value=default_name)
        entry = ttk.Entry(container, textvariable=name_var, width=52)
        entry.pack(fill="x")
        error_var = tk.StringVar()
        error_label = tk.Label(
            container,
            textvariable=error_var,
            bg="#f6f7fb",
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
                    value = validate_new_backup_name(config_dir, name_var.get(), source_signature)
                else:
                    value = validate_backup_name_format(name_var.get())
                    if named_backup_records(config_dir, value, exclude_path=rename_path):
                        raise BackupNameConflictError("已存在同名备份，请使用新的备份名称。")
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
                validate_new_backup_name(config_dir, default_name, source_signature)
            except BackupNameError as exc:
                error_var.set(str(exc))
        self.center_window(dialog, 440, 205, parent=target)
        entry.focus_set()
        entry.selection_range(0, "end")
        self.wait_window(dialog)
        return result["value"]

    def choose_backup_name(self, config_dir: Path, parent: tk.Toplevel | None = None) -> tuple[bool, str | None]:
        if not any((config_dir / file_name).exists() for file_name in ("auth.json", "config.toml")):
            return True, None
        provider_name = read_codex_config(config_dir).provider.strip() or DEFAULT_PROVIDER
        default_name = suggested_backup_name(config_dir)
        signature = build_backup_signature(config_dir)
        if find_reusable_backup(config_dir, default_name, signature) is not None:
            return True, default_name
        name = self.ask_backup_name(
            config_dir,
            default_name,
            f"当前备份配置：{provider_name}",
            parent=parent,
        )
        return (name is not None), name

    def backup_result_message(self, result: BackupResult) -> str:
        if result.status == "not_needed" or result.record is None:
            return "当前没有旧配置，无需备份。"
        created_at = result.record.created_at.strftime("%Y-%m-%d %H:%M:%S")
        action = "已创建备份" if result.status == "created" else "已复用备份"
        return f"{action}：{result.record.name}（{created_at}）"

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
        self.status_var.set("正在扫描常见位置...")
        self.update_idletasks()

        def worker() -> None:
            found = scan_common_locations()
            self.after(0, lambda: self._finish_scan(found))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_scan(self, found: list[Path]) -> None:
        if not found:
            self.status_var.set("没有扫描到配置目录，可以点击“浏览...”手动选择。")
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
        backup_result = None
        template_created = False
        template_canceled = False
        first_use = not (path / "auth.json").exists() and not (path / "config.toml").exists()
        state, issues = classify_config_for_editing(path)
        official_login_mode = is_official_login_mode(path)

        if state == "editable" and official_login_mode:
            set_official_login_mode(path, False)
            official_login_mode = False

        if state == "needs_template" and not official_login_mode:
            confirmed, backup_name = self.choose_backup_name(path)
            if not confirmed:
                template_canceled = True
            else:
                try:
                    backup_result = create_custom_template_config(
                        path,
                        None,
                        TEMPLATE_PROVIDER_NAME,
                        TEMPLATE_BASE_URL,
                        TEMPLATE_MODEL,
                        backup_name,
                    )
                    template_created = True
                    set_official_login_mode(path, False)
                except (OSError, BackupNameError) as exc:
                    self.show_error(f"自动创建模板失败：\n{exc}")
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
        save_settings(path)
        if template_canceled:
            self.status_var.set("已取消自动创建模板，原配置未修改。")
            return
        if template_created:
            backup_message = self.backup_result_message(backup_result)
            if first_use:
                self.status_var.set(f"检测到首次使用，已创建可编辑配置：{path}")
            else:
                self.status_var.set(f"已自动创建可编辑模板；{backup_message}；当前已使用配置：{config.provider}")
                self.show_info(
                    f"已自动创建可编辑模板。\n\n{backup_message}\n"
                    f"当前已使用配置：{config.provider}"
                )
            return
        if official_login_mode:
            if config.config_exists:
                self.status_var.set("已保留 Codex 官方登录配置；可直接打开 Codex 登录 GPT 账号。")
            else:
                self.status_var.set("已进入官方登录模式；请关闭本工具并启动 Codex，按提示登录 GPT 账号。")
            return
        markers = []
        markers.append("auth.json 已找到" if config.auth_exists else "auth.json 不存在")
        markers.append("config.toml 已找到" if config.config_exists else "config.toml 不存在")
        self.status_var.set(f"已读取：{path}（{'，'.join(markers)}）")
    def reload_current(self) -> None:
        self.load_path(self.current_path())

    def toggle_key_visibility(self) -> None:
        self.key_entry.configure(show="" if self.show_key_var.get() else "*")

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

        confirmed, backup_name = self.choose_backup_name(path)
        if not confirmed:
            self.status_var.set("已取消保存，当前配置未修改。")
            return

        if state == "needs_template":
            try:
                backup_result = create_custom_template_config(
                    path,
                    self.api_key_var.get(),
                    self.provider_var.get().strip(),
                    self.base_url_var.get(),
                    self.model_var.get(),
                    backup_name,
                )
            except (OSError, BackupNameError) as exc:
                self.show_error(f"保存失败：\n{exc}")
                return
            set_official_login_mode(path, False)
            backup_message = self.backup_result_message(backup_result)
            active_provider = self.provider_var.get().strip()
            self.status_var.set(
                f"保存成功，已自动创建可编辑 API 配置；{backup_message}；当前已使用配置：{active_provider}"
            )
            self.show_info(
                f"配置保存成功，已自动创建可编辑 API 配置。\n\n{backup_message}\n"
                f"当前已使用配置：{active_provider}\n"
                "重新打开 Codex 后通常会读取新配置。"
            )
            return

        try:
            backup_result = save_codex_config(
                path,
                self.api_key_var.get(),
                self.provider_var.get().strip(),
                self.base_url_var.get(),
                self.model_var.get(),
                backup_name,
            )
        except (OSError, BackupNameError) as exc:
            self.show_error(f"保存失败：\n{exc}")
            return
        set_official_login_mode(path, False)
        backup_message = self.backup_result_message(backup_result)
        active_provider = self.provider_var.get().strip()
        self.status_var.set(f"保存成功；{backup_message}；当前已使用配置：{active_provider}")
        self.show_info(
            f"配置保存成功。\n\n{backup_message}\n"
            f"当前已使用配置：{active_provider}\n"
            "重新打开 Codex 后通常会读取新配置。"
        )

    def restore_defaults(self) -> None:
        message = (
            "确定恢复默认配置吗？\n\n"
            "此功能适用于准备登录自己的 ChatGPT/GPT 账号。\n"
            "软件会先备份，然后删除 auth.json 和 config.toml。\n"
            "不会删除聊天记录、本地数据库和已有备份。\n\n"
            "恢复后请关闭本工具并启动 Codex，按提示登录。"
        )
        if not self.ask_yes_no(message):
            return
        confirmed, backup_name = self.choose_backup_name(self.current_path())
        if not confirmed:
            self.status_var.set("已取消恢复默认配置，当前配置未修改。")
            return
        try:
            backup_result = restore_default_config(self.current_path(), backup_name)
        except (OSError, BackupNameError) as exc:
            self.show_error(f"恢复失败：\n{exc}")
            return

        set_official_login_mode(self.current_path(), True)
        self.api_key_var.set("")
        self.provider_var.set(DEFAULT_PROVIDER)
        self.base_url_var.set(DEFAULT_BASE_URL)
        self.model_var.set(TEMPLATE_MODEL)
        backup_message = self.backup_result_message(backup_result)
        self.status_var.set(f"已进入官方登录模式；{backup_message}")
        self.show_info(
            f"已恢复默认配置。\n\n{backup_message}\n"
            "当前已使用配置：官方登录模式\n"
            "请关闭本工具并启动 Codex，按提示登录自己的 GPT 账号。"
        )

    def show_backup_settings(self) -> None:
        config_dir = self.current_path()
        dialog = tk.Toplevel(self)
        dialog.title("备份设置")
        dialog.transient(self)
        dialog.grab_set()
        dialog.minsize(620, 360)

        container = ttk.Frame(dialog, padding=16)
        container.pack(fill="both", expand=True)
        ttk.Label(
            container,
            text="管理已有备份。右击备份可以编辑名称、删除或进入多选模式。",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 10))

        tree_frame = ttk.Frame(container)
        tree_frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(
            tree_frame,
            columns=("name", "created_at"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        tree.heading("name", text="备份名称")
        tree.heading("created_at", text="创建时间")
        tree.column("name", minwidth=260, width=360, anchor="w")
        tree.column("created_at", minwidth=150, width=170, anchor="center", stretch=False)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        empty_var = tk.StringVar()
        ttk.Label(container, textvariable=empty_var, style="Hint.TLabel").pack(anchor="w", pady=(8, 0))

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(14, 0))
        button_row.columnconfigure(3, weight=1)
        records_by_item: dict[str, BackupRecord] = {}
        multi_mode = {"value": False}
        drag_state = {
            "active": False,
            "anchor": None,
            "base_selection": (),
            "press_y": 0,
            "last_y": 0,
            "moved": False,
            "scroll_job": None,
        }

        def selected_records() -> list[BackupRecord]:
            return [records_by_item[item] for item in tree.selection() if item in records_by_item]

        def update_buttons() -> None:
            selection_count = len(selected_records())
            item_count = len(records_by_item)
            restore_button.configure(state="normal" if selection_count == 1 else "disabled")
            delete_selected_button.configure(state="normal" if selection_count > 0 else "disabled")
            select_all_button.configure(
                text="取消全选" if item_count > 0 and selection_count == item_count else "全选",
                state="normal" if item_count > 0 else "disabled",
            )

        def refresh(select_path: Path | None = None) -> None:
            records_by_item.clear()
            for item in tree.get_children():
                tree.delete(item)
            selected_item = None
            for index, record in enumerate(list_backup_records(config_dir)):
                item = f"backup-{index}"
                records_by_item[item] = record
                tree.insert(
                    "",
                    "end",
                    iid=item,
                    values=(record.name, record.created_at.strftime("%Y-%m-%d %H:%M:%S")),
                )
                if select_path is not None and normalized_path_key(record.path) == normalized_path_key(select_path):
                    selected_item = item
            empty_var.set("暂无可用备份。" if not records_by_item else "备份不会自动删除，将一直保留到你手动删除。")
            if selected_item is not None:
                tree.selection_set(selected_item)
                tree.focus(selected_item)
            elif records_by_item and not multi_mode["value"]:
                first_item = next(iter(records_by_item))
                tree.selection_set(first_item)
                tree.focus(first_item)
            update_buttons()

        def set_multi_mode(enabled: bool) -> None:
            cancel_drag()
            multi_mode["value"] = enabled
            tree.configure(selectmode="extended" if enabled else "browse")
            if enabled:
                select_all_button.grid()
                delete_selected_button.grid()
                exit_multi_button.grid()
            else:
                selection = tree.selection()
                if len(selection) > 1:
                    tree.selection_set(selection[0])
                select_all_button.grid_remove()
                delete_selected_button.grid_remove()
                exit_multi_button.grid_remove()
            update_buttons()

        def toggle_select_all() -> None:
            if not multi_mode["value"]:
                return
            items = tree.get_children()
            if items and len(tree.selection()) == len(items):
                tree.selection_remove(*items)
            else:
                tree.selection_set(items)
                if items:
                    tree.focus(items[0])
            update_buttons()

        def on_select_all_shortcut(_event) -> str | None:
            if not multi_mode["value"]:
                return None
            toggle_select_all()
            return "break"

        def edit_record(record: BackupRecord) -> None:
            new_name = self.ask_backup_name(
                config_dir,
                record.name,
                f"修改备份名称：{record.name}",
                parent=dialog,
                rename_path=record.path,
            )
            if new_name is None:
                return
            try:
                renamed = rename_backup(config_dir, record.path, new_name)
            except (OSError, BackupNameError) as exc:
                self.show_error(f"修改备份名称失败：\n{exc}", parent=dialog)
                return
            refresh(renamed.path)

        def remove_records(records: list[BackupRecord]) -> None:
            if not records:
                return
            if len(records) == 1:
                message = f"确定永久删除这个备份吗？\n\n{records[0].name}"
            else:
                message = f"确定永久删除所选的 {len(records)} 个备份吗？\n\n删除后无法恢复。"
            if not self.ask_yes_no(message, parent=dialog):
                return
            try:
                delete_backups(config_dir, [record.path for record in records])
            except OSError as exc:
                self.show_error(f"删除备份失败：\n{exc}", parent=dialog)
                return
            refresh()

        def restore_selected() -> None:
            records = selected_records()
            if len(records) != 1:
                return
            selected = records[0]
            if not self.ask_yes_no(
                f"确定恢复这个备份吗？\n\n{selected.name}\n{selected.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                parent=dialog,
            ):
                return
            confirmed, backup_name = self.choose_backup_name(config_dir, parent=dialog)
            if not confirmed:
                self.status_var.set("已取消恢复备份，当前配置未修改。")
                return
            try:
                backup_result = restore_backup(config_dir, selected.path, backup_name)
            except (OSError, BackupNameError) as exc:
                self.show_error(f"恢复失败：\n{exc}", parent=dialog)
                return

            restored_state, _issues = classify_config_for_editing(config_dir)
            official_mode = restored_state == "needs_template"
            set_official_login_mode(config_dir, official_mode)
            restored_config = read_codex_config(config_dir)
            active_config = "官方登录模式" if official_mode else restored_config.provider
            backup_message = self.backup_result_message(backup_result)
            dialog.destroy()
            self.reload_current()
            self.status_var.set(f"已恢复备份：{selected.name}；{backup_message}；当前已使用配置：{active_config}")
            self.show_info(
                f"备份已恢复：{selected.name}\n\n{backup_message}\n"
                f"当前已使用配置：{active_config}\n"
                "重新打开 Codex 后通常会读取恢复后的配置。"
            )

        def cancel_drag() -> None:
            scroll_job = drag_state["scroll_job"]
            if scroll_job is not None:
                try:
                    tree.after_cancel(scroll_job)
                except tk.TclError:
                    pass
            drag_state.update(
                {
                    "active": False,
                    "anchor": None,
                    "base_selection": (),
                    "moved": False,
                    "scroll_job": None,
                }
            )

        def apply_drag_selection(current_item: str) -> None:
            anchor = drag_state["anchor"]
            if anchor is None:
                return
            selection = drag_selection_items(
                tree.get_children(),
                anchor,
                current_item,
                drag_state["base_selection"],
            )
            tree.selection_set(selection)
            tree.focus(current_item)
            tree.see(current_item)
            update_buttons()

        def auto_scroll_drag() -> None:
            drag_state["scroll_job"] = None
            if not drag_state["active"] or not drag_state["moved"] or not tree.winfo_exists():
                return
            height = tree.winfo_height()
            y = drag_state["last_y"]
            direction = -1 if y < 28 else 1 if y > height - 24 else 0
            if direction == 0:
                return
            tree.yview_scroll(direction, "units")
            target_y = max(24, min(y, height - 2))
            current_item = tree.identify_row(target_y)
            if current_item:
                apply_drag_selection(current_item)
            drag_state["scroll_job"] = tree.after(90, auto_scroll_drag)

        def schedule_drag_scroll() -> None:
            height = tree.winfo_height()
            y = drag_state["last_y"]
            near_edge = y < 28 or y > height - 24
            if near_edge and drag_state["scroll_job"] is None:
                drag_state["scroll_job"] = tree.after(90, auto_scroll_drag)
            elif not near_edge and drag_state["scroll_job"] is not None:
                try:
                    tree.after_cancel(drag_state["scroll_job"])
                except tk.TclError:
                    pass
                drag_state["scroll_job"] = None

        def on_tree_press(event) -> str | None:
            if not multi_mode["value"]:
                return None
            item = tree.identify_row(event.y)
            if not item:
                return "break"
            drag_state.update(
                {
                    "active": True,
                    "anchor": item,
                    "base_selection": tree.selection(),
                    "press_y": event.y,
                    "last_y": event.y,
                    "moved": False,
                }
            )
            return "break"

        def on_tree_motion(event) -> str | None:
            if not multi_mode["value"] or not drag_state["active"]:
                return None
            drag_state["last_y"] = event.y
            current_item = tree.identify_row(event.y)
            if abs(event.y - drag_state["press_y"]) >= 4 or current_item != drag_state["anchor"]:
                drag_state["moved"] = True
            if drag_state["moved"] and current_item:
                apply_drag_selection(current_item)
            schedule_drag_scroll()
            return "break"

        def on_tree_release(_event) -> str | None:
            if not multi_mode["value"] or not drag_state["active"]:
                return None
            anchor = drag_state["anchor"]
            base_selection = drag_state["base_selection"]
            moved = drag_state["moved"]
            cancel_drag()
            if not moved and anchor is not None:
                if anchor in base_selection:
                    tree.selection_remove(anchor)
                else:
                    tree.selection_add(anchor)
                    tree.focus(anchor)
            update_buttons()
            return "break"

        def show_context_menu(event) -> None:
            item = tree.identify_row(event.y)
            if not item or item not in records_by_item:
                return
            if multi_mode["value"]:
                if item not in tree.selection():
                    tree.selection_add(item)
            else:
                tree.selection_set(item)
            tree.focus(item)
            update_buttons()
            record = records_by_item[item]
            menu = tk.Menu(dialog, tearoff=False)
            menu.add_command(label="编辑", command=lambda: edit_record(record))
            menu.add_command(label="删除", command=lambda: remove_records([record]))
            menu.add_separator()
            menu.add_command(
                label="退出多选" if multi_mode["value"] else "多选",
                command=lambda: set_multi_mode(not multi_mode["value"]),
            )
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        select_all_button = ttk.Button(
            button_row,
            text="全选",
            command=toggle_select_all,
            style="Compact.TButton",
            width=10,
        )
        select_all_button.grid(row=0, column=0, padx=(0, 8))
        delete_selected_button = ttk.Button(
            button_row,
            text="删除所选备份",
            command=lambda: remove_records(selected_records()),
            style="Compact.TButton",
            width=14,
        )
        delete_selected_button.grid(row=0, column=1, padx=(0, 8))
        exit_multi_button = ttk.Button(
            button_row,
            text="退出多选",
            command=lambda: set_multi_mode(False),
            style="Compact.TButton",
            width=10,
        )
        exit_multi_button.grid(row=0, column=2)
        restore_button = ttk.Button(
            button_row,
            text="恢复选中备份",
            command=restore_selected,
            style="Compact.TButton",
            width=14,
        )
        restore_button.grid(row=0, column=4, padx=(0, 8))
        ttk.Button(
            button_row,
            text="关闭",
            command=dialog.destroy,
            style="Compact.TButton",
            width=9,
        ).grid(row=0, column=5)

        tree.bind("<<TreeviewSelect>>", lambda _event: update_buttons())
        tree.bind("<ButtonPress-1>", on_tree_press, add="+")
        tree.bind("<B1-Motion>", on_tree_motion, add="+")
        tree.bind("<ButtonRelease-1>", on_tree_release, add="+")
        tree.bind("<Button-3>", show_context_menu)
        dialog.bind("<Control-a>", on_select_all_shortcut)
        dialog.bind("<Escape>", lambda _event: set_multi_mode(False) if multi_mode["value"] else dialog.destroy())
        set_multi_mode(False)
        refresh()
        self.center_window(dialog, 660, 410)
        tree.focus_set()

    def open_backup_dir(self) -> None:
        backup_dir = self.current_path() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(backup_dir))


def main() -> None:
    app = CodexConfigApp()
    app.mainloop()


if __name__ == "__main__":
    main()
