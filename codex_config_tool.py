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
APP_VERSION = "1.0.0"
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
MAX_BACKUPS = 5
SETTINGS_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "CodexConfigTool"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
OFFICIAL_LOGIN_MODE_PATH_KEY = "official_login_mode_path"
HIDE_ONBOARDING_KEY = "hide_onboarding"


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


class ConfigConflictError(OSError):
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
            return bytes(value[1:-1], "utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
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


def sanitize_backup_name(name: str) -> str:
    name = name.strip()
    if not name:
        return "backup"
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    sanitized = re.sub(r"\s+", "_", sanitized).strip("._ ")
    return sanitized[:40] or "backup"


def backup_sort_key(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0


def list_backups(config_dir: Path) -> list[Path]:
    backup_root = config_dir / "backups"
    if not backup_root.exists():
        return []
    return sorted(
        [item for item in backup_root.iterdir() if item.is_dir() and ((item / "auth.json").exists() or (item / "config.toml").exists())],
        key=backup_sort_key,
        reverse=True,
    )


def prune_backups(config_dir: Path) -> None:
    backups = list_backups(config_dir)
    for backup in backups[MAX_BACKUPS:]:
        shutil.rmtree(backup, ignore_errors=True)


def create_backup(config_dir: Path, name: str = "", prune: bool = True) -> Path:
    backup_root = config_dir / "backups"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = sanitize_backup_name(name)
    backup_dir = backup_root / f"{timestamp}-{backup_name}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for file_name in ("auth.json", "config.toml"):
        source = config_dir / file_name
        if source.exists():
            shutil.copy2(source, backup_dir / file_name)
    if prune:
        prune_backups(config_dir)
    return backup_dir


def restore_backup(config_dir: Path, backup_dir: Path) -> Path:
    safety_backup = create_backup(config_dir, "before-restore", prune=False)
    for file_name in ("auth.json", "config.toml"):
        source = backup_dir / file_name
        target = config_dir / file_name
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
    save_settings(config_dir)
    prune_backups(config_dir)
    return safety_backup


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


def save_codex_config(config_dir: Path, api_key: str, display_name: str, base_url: str, model: str) -> Path:
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

    backup_dir = create_backup(config_dir, "before-save")
    update_auth_json(auth_path, api_key)
    update_existing_config_toml(config_path, display_name, base_url, model)
    save_settings(config_dir)
    return backup_dir


def save_fresh_codex_config(config_dir: Path, api_key: str, provider: str, base_url: str) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = create_backup(config_dir, "before-save")
    auth_path = config_dir / "auth.json"
    auth_data = {}
    if api_key.strip():
        auth_data["OPENAI_API_KEY"] = api_key.strip()
    auth_path.write_text(json.dumps(auth_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    config_path = config_dir / "config.toml"
    write_text(config_path, build_fresh_config_toml(api_key, provider, base_url))
    save_settings(config_dir)
    return backup_dir


def restore_default_config(config_dir: Path) -> Path | None:
    config_dir.mkdir(parents=True, exist_ok=True)
    has_existing_config = any((config_dir / file_name).exists() for file_name in ("auth.json", "config.toml"))
    backup_dir = create_backup(config_dir, "before-default") if has_existing_config else None
    for file_name in ("auth.json", "config.toml"):
        path = config_dir / file_name
        if path.exists():
            path.unlink()
    save_settings(config_dir)
    return backup_dir


def create_custom_template_config(config_dir: Path, api_key: str | None, provider_name: str, base_url: str, model: str) -> Path | None:
    config_dir.mkdir(parents=True, exist_ok=True)
    has_existing_config = any((config_dir / file_name).exists() for file_name in ("auth.json", "config.toml"))
    backup_dir = create_backup(config_dir, "before-template") if has_existing_config else None
    auth_path = config_dir / "auth.json"
    if api_key is None:
        if not auth_path.exists():
            auth_path.write_text("{}\n", encoding="utf-8")
    else:
        update_auth_json(auth_path, api_key)
    write_text(config_dir / "config.toml", build_custom_template_config_toml(provider_name, base_url, model))
    save_settings(config_dir)
    return backup_dir

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
        path_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(path_frame, text="浏览...", command=self.choose_path).grid(row=1, column=1, padx=(0, 8))
        ttk.Button(path_frame, text="扫描", command=self.scan_paths).grid(row=1, column=2)
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
            ("备份配置", self.backup_current),
            ("恢复备份", self.restore_backup_dialog),
            ("打开备份目录", self.open_backup_dir),
            ("恢复默认配置", self.restore_defaults),
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
        parent = parent or self
        parent.update_idletasks()
        window.update_idletasks()
        if width is None:
            width = window.winfo_reqwidth()
        if height is None:
            height = window.winfo_reqheight()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + max((parent_width - width) // 2, 0)
        y = parent_y + max((parent_height - height) // 2, 0)
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
        if not force and settings.get(HIDE_ONBOARDING_KEY, False):
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
            ("2", "点击“保存配置”。保存前，软件会自动备份原来的配置。"),
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
        ).pack(anchor="w", pady=(0, 14))

        hide_var = tk.BooleanVar(value=bool(settings.get(HIDE_ONBOARDING_KEY, False)))
        ttk.Checkbutton(container, text="下次不再提示", variable=hide_var).pack(anchor="w")

        def close() -> None:
            save_setting_value(HIDE_ONBOARDING_KEY, bool(hide_var.get()))
            dialog.destroy()
            self.lift()
            self.focus_force()

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(16, 0))
        tk.Button(
            button_row,
            text="开始使用",
            command=close,
            bg="#1f7ed0",
            fg="#ffffff",
            activebackground="#1768ad",
            activeforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=18,
            pady=7,
        ).pack(side="right")

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Return>", lambda _event: close())
        dialog.bind("<Escape>", lambda _event: close())
        self.center_window(dialog, 520, 390)
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
        ).pack(pady=(0, 10))

        button_row = ttk.Frame(container)
        button_row.pack(fill="x")

        def open_onboarding() -> None:
            dialog.destroy()
            self.after(50, lambda: self.show_onboarding_dialog(force=True))

        ttk.Button(
            button_row,
            text="新手引导",
            command=open_onboarding,
            style="Compact.TButton",
            width=10,
        ).pack(side="left")
        ttk.Button(
            button_row,
            text="关闭",
            command=dialog.destroy,
            style="Compact.TButton",
            width=10,
        ).pack(side="right")

        dialog.bind("<Return>", lambda _event: dialog.destroy())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.center_window(dialog, 560, 250)
        dialog.focus_force()
    def ask_backup_name(self) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title(APP_NAME)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        container = ttk.Frame(dialog, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="请输入备份名称：").pack(anchor="w", pady=(0, 8))
        name_var = tk.StringVar(value="manual")
        entry = ttk.Entry(container, textvariable=name_var, width=52)
        entry.pack(fill="x")

        result = {"value": None}

        def accept() -> None:
            result["value"] = name_var.get()
            dialog.destroy()

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(16, 0))
        ttk.Button(button_row, text="取消", command=dialog.destroy, style="Compact.TButton", width=9).pack(side="right")
        ttk.Button(button_row, text="确定", command=accept, style="Compact.TButton", width=9).pack(side="right", padx=(0, 8))

        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        self.center_window(dialog, 420, 150)
        entry.focus_set()
        entry.selection_range(0, "end")
        self.wait_window(dialog)
        return result["value"]

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
        auto_backup = None
        template_created = False
        first_use = not (path / "auth.json").exists() and not (path / "config.toml").exists()
        state, issues = classify_config_for_editing(path)
        official_login_mode = is_official_login_mode(path)

        if state == "editable" and official_login_mode:
            set_official_login_mode(path, False)
            official_login_mode = False

        if state == "needs_template" and not official_login_mode:
            try:
                auto_backup = create_custom_template_config(
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
        if template_created:
            if first_use:
                self.status_var.set(f"检测到首次使用，已创建可编辑配置：{path}")
            else:
                self.status_var.set(f"已自动创建可编辑模板；原配置已自动备份到：{auto_backup}")
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

        if state == "needs_template":
            try:
                backup_dir = create_custom_template_config(
                    path,
                    self.api_key_var.get(),
                    self.provider_var.get().strip(),
                    self.base_url_var.get(),
                    self.model_var.get(),
                )
            except OSError as exc:
                self.show_error(f"保存失败：\n{exc}")
                return
            set_official_login_mode(path, False)
            if backup_dir is None:
                self.status_var.set("保存成功，已自动创建可编辑 API 配置；当前没有旧配置，无需备份。")
                backup_message = "当前没有旧配置，无需备份。"
            else:
                self.status_var.set(f"保存成功，已自动创建可编辑 API 配置；原配置已备份到：{backup_dir}")
                backup_message = f"原配置已自动备份：{backup_dir.name}"
            self.show_info(
                f"配置保存成功，已自动创建可编辑 API 配置。\n\n{backup_message}\n"
                "重新打开 Codex 后通常会读取新配置。"
            )
            return

        try:
            backup_dir = save_codex_config(
                path,
                self.api_key_var.get(),
                self.provider_var.get().strip(),
                self.base_url_var.get(),
                self.model_var.get(),
            )
        except OSError as exc:
            self.show_error(f"保存失败：\n{exc}")
            return
        set_official_login_mode(path, False)
        self.status_var.set(f"保存成功，原配置已自动备份到：{backup_dir}")
        self.show_info(
            f"配置保存成功。\n\n原配置已自动备份：{backup_dir.name}\n"
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
        try:
            backup_dir = restore_default_config(self.current_path())
        except OSError as exc:
            self.show_error(f"恢复失败：\n{exc}")
            return

        set_official_login_mode(self.current_path(), True)
        self.api_key_var.set("")
        self.provider_var.set(DEFAULT_PROVIDER)
        self.base_url_var.set(DEFAULT_BASE_URL)
        self.model_var.set(TEMPLATE_MODEL)
        if backup_dir is None:
            self.status_var.set("已进入官方登录模式；当前没有旧配置，无需备份。")
            backup_message = "当前没有旧配置，无需备份。"
        else:
            self.status_var.set(f"已进入官方登录模式；原配置已自动备份到：{backup_dir}")
            backup_message = f"原配置已自动备份：{backup_dir.name}"
        self.show_info(
            f"已恢复默认配置并进入官方登录模式。\n\n{backup_message}\n"
            "请关闭本工具并启动 Codex，按提示登录自己的 GPT 账号。"
        )
    def backup_current(self) -> None:
        name = self.ask_backup_name()
        if name is None:
            return
        try:
            backup_dir = create_backup(self.current_path(), name)
        except OSError as exc:
            self.show_error(f"备份失败：\n{exc}")
            return
        self.status_var.set(f"备份成功：{backup_dir}")
        self.show_info(f"当前配置已备份。\n最多保留 {MAX_BACKUPS} 个备份。")

    def restore_backup_dialog(self) -> None:
        backups = list_backups(self.current_path())
        if not backups:
            self.show_info("当前配置目录还没有可恢复的备份。")
            return

        picker = tk.Toplevel(self)
        picker.title("恢复备份")
        picker.transient(self)
        picker.grab_set()
        ttk.Label(picker, text="选择一个备份进行恢复。恢复前会自动备份当前配置。").pack(anchor="w", padx=16, pady=(16, 8))
        listbox = tk.Listbox(picker, height=6, font=("Consolas", 10))
        listbox.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for backup in backups:
            listbox.insert("end", backup.name)
        listbox.selection_set(0)

        button_row = ttk.Frame(picker)
        button_row.pack(fill="x", padx=16, pady=(0, 16))

        def accept() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            backup = backups[selection[0]]
            if not self.ask_yes_no(f"确定恢复这个备份吗？\n{backup.name}", parent=picker):
                return
            try:
                safety_backup = restore_backup(self.current_path(), backup)
            except OSError as exc:
                self.show_error(f"恢复失败：\n{exc}", parent=picker)
                return
            picker.destroy()
            restored_state, _issues = classify_config_for_editing(self.current_path())
            set_official_login_mode(self.current_path(), restored_state == "needs_template")
            self.reload_current()
            self.status_var.set(f"已恢复备份：{backup.name}；恢复前配置已自动备份到：{safety_backup}")
            self.show_info(
                f"备份已恢复。\n\n恢复前配置已自动备份：{safety_backup.name}\n"
                "重新打开 Codex 后通常会读取恢复后的配置。"
            )

        ttk.Button(button_row, text="取消", command=picker.destroy, style="Compact.TButton", width=9).pack(side="right", padx=(8, 0))
        ttk.Button(button_row, text="恢复选中备份", command=accept, style="Compact.TButton", width=14).pack(side="right")
        self.center_window(picker, 520, 280)

    def open_backup_dir(self) -> None:
        backup_dir = self.current_path() / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(backup_dir))


def main() -> None:
    app = CodexConfigApp()
    app.mainloop()


if __name__ == "__main__":
    main()
