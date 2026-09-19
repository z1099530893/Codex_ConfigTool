# Codex 配置助手 v1.4.0

本版本完善供应商模型列表、配置切换生命周期、官方登录数据保护、推荐渠道和 Windows 安装体验。安装版与便携版同时提供。

## 下载

- `CodexConfigTool-Setup-v1.4.0.exe`：推荐，按当前用户安装，支持开始菜单、可选桌面快捷方式和标准卸载流程。
- `CodexConfigTool-Portable-v1.4.0.exe`：便携版，无需安装。

## 新增与改进

- 在新增、编辑配置时可从第三方供应商的 OpenAI 兼容 `/models` 接口获取模型，支持下拉选择和手动输入；OpenAI/Codex 原生模型无需获取列表，由 Codex 自身管理模型与推理能力。
- 获取结果只保留在编辑事务中，点击保存后才与连接信息、启动默认模型和完整模型列表一起原子落盘。
- 当前配置页改为只读；新增、编辑只保存配置库，双击配置统一负责应用、启动和必要的自动重启。
- 每个第三方 Provider 独立保存启动默认模型、默认推理强度和模型目录；官方 OpenAI Provider 完全使用 Codex 原生模型与推理能力。
- 新增 AI Ark API 和 JM2 API 推荐渠道，使用本地网站图标并通过系统默认浏览器打开。
- 新增后台更新检查和关于页手动检查；发现新版本时只显示关于图标红点，不弹窗、不自动下载。
- 新增 Windows 安装包，桌面快捷方式默认选中并可在安装时取消。

![当前配置](https://raw.githubusercontent.com/z1099530893/Codex_ConfigTool/v1.4.0/docs/images/current-config.png)

![推荐渠道](https://raw.githubusercontent.com/z1099530893/Codex_ConfigTool/v1.4.0/docs/images/recommended-channel.png)

## 重要修复

- 修复进入官方登录模式时删除 `auth.json` 或 `config.toml`，造成配置、登录状态或对话上下文丢失的问题。
- API 配置与官方登录改为非破坏性字段合并，保留聊天记录、会话数据、ChatGPT 登录令牌和未知配置字段。
- 修复运行中切换配置时旧 Codex 实例可能把内存中的配置反写到目标配置的问题；现在先正常退出，再同步、投影并从 Windows 正式入口启动。
- 双击当前配置在 Codex 未运行时可以直接启动；编辑活动配置后不会被旧 live 配置反向覆盖；运行且无修改时不会重复重启。
- 切换取消或失败时保持零写入或恢复 live 配置、配置库和待应用标记，不使用 `taskkill` 强制结束 Codex。
- 修复 OpenAI 原生配置误用第三方模型目录导致模型名称或推理档位缺失的问题。
- 修复配置助手启动 Codex 后任务栏或系统托盘图标异常的问题，并确认新主进程和窗口后才报告成功。
- 修复主程序同时显示原生标题栏和自绘标题栏、安装器中文文本及卸载窗口问题。

## 安装与数据安全

- 安装包默认安装到 `%LOCALAPPDATA%\Programs\CodexConfigTool`，不要求管理员权限。
- 覆盖安装不会删除 Codex 配置、API Key 或聊天记录。
- 卸载时默认“保留用户数据”。
- 选择“完全删除用户数据”时，仅删除 `%APPDATA%\CodexConfigTool` 和 `%USERPROFILE%\.codex\backups`。
- 卸载器不会扫描或删除 `%APPDATA%\Codex`、`%LOCALAPPDATA%\Codex`，也不会删除 `.codex` 根目录中的 `auth.json`、`config.toml`、`sessions`、`archived_sessions` 或 `history.jsonl`。
- 请勿使用第三方卸载工具清理 Codex 相关“残留”，以免误删 Codex 自身目录。

## 使用说明

完整功能介绍、全部界面截图和数据边界请查看项目 [README](https://github.com/z1099530893/Codex_ConfigTool#readme)。

## 文件校验

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `CodexConfigTool-Setup-v1.4.0.exe` | 15,304,391 字节 | `c0d90482f360e8ed1a1b9bfdc634ddcd3b6b5e608e9fb71f9511a0d8d4ad37b5` |
| `CodexConfigTool-Portable-v1.4.0.exe` | 13,538,969 字节 | `a82178a70f12ae537bae86f8f2d31048094040919e2b3d8f2fad960c895e8dce` |

验证环境：Windows 10 x64、Python 3.12、PyInstaller 6.20.0、Inno Setup 6.7.3。Python 语法检查、完整自动化测试、安装器检查、单文件构建和隔离启动验证均通过。
