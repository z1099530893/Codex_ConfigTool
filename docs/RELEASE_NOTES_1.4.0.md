# Codex 配置助手 v1.4.0

本版本新增供应商模型列表、推荐渠道和 Windows 安装包，并重点修复官方登录切换导致配置与对话数据丢失的问题。安装版与便携版同时提供。

## 下载

- `CodexConfigTool-Setup-v1.4.0.exe`：推荐，按当前用户安装，支持开始菜单、可选桌面快捷方式和标准卸载流程。
- `CodexConfigTool-Portable-v1.4.0.exe`：便携版，无需安装。

## 新增功能

- 从当前 API 供应商的 OpenAI 兼容 `/models` 接口获取可用模型。
- Model 同时支持下拉选择和手动输入，修改后自动保存到当前配置。
- 新增“推荐渠道”页面，可使用默认浏览器打开 AI Ark API。
- 新增启动后台更新检查和关于页手动检查；发现新版本时只显示关于图标红点，不弹窗、不自动下载。
- 新增 Windows 安装包，桌面快捷方式默认选中并可在安装时取消。

![当前配置与模型选择](https://raw.githubusercontent.com/z1099530893/Codex_ConfigTool/main/docs/images/current-config.png)

![推荐渠道](https://raw.githubusercontent.com/z1099530893/Codex_ConfigTool/main/docs/images/recommended-channel.png)

## 重要修复

- 修复进入官方登录模式时删除 `auth.json` 或 `config.toml`，造成配置、登录状态或对话上下文丢失的问题。
- API 配置、官方登录和新 API 之间改为非破坏性字段合并，保留聊天记录、会话数据、ChatGPT 登录令牌和未知配置字段。
- 修复通过配置助手重启 Codex 后系统托盘图标缺失、只能从任务管理器结束进程的问题。
- 修复更新检查使用 GitHub REST API 时可能出现 HTTP 403 的问题。
- 修复主程序同时显示原生标题栏和自绘标题栏的问题。
- 修复安装界面中文文本、快捷方式助记键和卸载窗口运行错误。
- 修复模型输入框和下拉框右侧边线不一致，以及配置名称和 Base URL 区域无法双击切换的问题。

## 安装与数据安全

- 安装包默认安装到 `%LOCALAPPDATA%\Programs\CodexConfigTool`，不要求管理员权限。
- 覆盖安装不会删除 Codex 配置、API Key 或聊天记录。
- 卸载时默认“保留用户数据”。
- 选择“完全删除用户数据”时，仅删除 `%APPDATA%\CodexConfigTool` 和 `%USERPROFILE%\.codex\backups`。
- 卸载器不会扫描或删除 `%APPDATA%\Codex`、`%LOCALAPPDATA%\Codex`，也不会删除 `.codex` 根目录中的 `auth.json`、`config.toml`、`sessions`、`archived_sessions` 或 `history.jsonl`。
- 请勿使用第三方卸载工具清理 Codex 相关“残留”，以免它误删 Codex 自身目录。

## 使用说明

完整功能介绍、界面截图和数据边界请查看项目 [README](https://github.com/z1099530893/Codex_ConfigTool#readme)。

## 文件校验

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `CodexConfigTool-Setup-v1.4.0.exe` | 14,822,967 字节 | `dd1e30898ebd5e87569611d56327e519a50c10af8417b7ef3bfac1a03d54db5c` |
| `CodexConfigTool-Portable-v1.4.0.exe` | 13,021,751 字节 | `ea372ae24f250c4a7654456c67efc2d6ae433c8e930f8a851695271b74c8311d` |

验证环境：Windows 10、Python 3.13.9、PyInstaller 6.20.0、Inno Setup 6.7.3。Python 语法检查、68 项自动测试及安装器真实编译均通过。
