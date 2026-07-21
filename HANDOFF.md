# Codex 配置助手开发交接

## 当前状态

- 版本：1.0.0
- 作者：k.x
- 联系邮箱：1099530893@qq.com
- 项目地址：https://github.com/z1099530893/Codex_ConfigTool
- 技术栈：Python 标准库、Tkinter、PyInstaller
- 主程序：`codex_config_tool.py`
- 平台：Windows

本项目用于安全修改 Codex 的 `auth.json` 和 `config.toml`。目标用户不了解 TOML 和 Codex 配置结构，因此正常流程应尽量自动化，同时对复杂或冲突配置保持保守。

## 核心状态机

### 可编辑配置

当 `config.toml` 中存在唯一的顶层 `model_provider`，且对应 `[model_providers.<id>]` 段中的 `name` 和 `base_url` 均可唯一定位时，状态为 `editable`。

普通保存只修改：

- `auth.json` 中的 `OPENAI_API_KEY`
- 当前 Provider 段中的 `name`
- 当前 Provider 段中的 `base_url`
- 顶层 `model`

普通保存不得修改顶层 Provider ID 或重命名 Provider 段。

### 需要模板

缺少 `config.toml`、缺少 Provider 定位信息或处于干净的官方 `openai` 状态时，状态为 `needs_template`。

- 普通模式：启动时自动备份已有文件并创建自定义模板
- 完全没有旧文件：直接创建，不生成空备份
- 点击保存时仍是该状态：按输入框内容自动创建模板并完成保存

固定模板使用：

```toml
model_provider = "newapi"
[model_providers.newapi]
```

不要随普通保存更改这两个 ID。

### 官方登录模式

“恢复默认配置”用于让用户登录自己的 ChatGPT/GPT 账号：

1. 备份已有的 `auth.json` 和 `config.toml`
2. 删除这两个文件
3. 不触碰 `sessions/`、`archived_sessions/`、`state_*.sqlite`、`logs_*.sqlite`、日志或备份目录
4. 在 `%APPDATA%\CodexConfigTool\settings.json` 中持久化 `official_login_mode_path`
5. 等待 Codex 自己生成官方配置并完成登录

官方登录模式在应用关闭和电脑重启后仍然有效。用户填写 API 配置并点击保存后，程序自动创建模板并清除该模式。

### 冲突配置

重复顶层字段、重复 Provider 段、重复 `name`/`base_url` 或无法唯一定位的结构属于 `conflict`。应用不得猜测或自动覆盖，应向用户显示冲突原因。

## 安全约束

- 修改前自动备份；没有旧文件时不创建空备份
- 最多保留 5 个常规备份
- 自动初始化必须完整保留已有 `auth.json` 的登录和认证字段
- 普通保存不能改变 `model_provider` 和 `[model_providers.xxx]` 段名
- 恢复默认只能删除 `auth.json` 和 `config.toml`
- 不得删除或迁移聊天记录、SQLite 数据库、日志和 Codex 运行目录
- 不得把 API Key 写入项目文件、日志或远程服务
- 复杂配置必须停止自动处理

实验结论：改变 `model_provider` 的 Provider ID，以及对应 `[model_providers.xxx]` 段名，可能导致 Codex 桌面端聊天窗口丢失或隐藏。

## 关键代码入口

- `classify_config_for_editing`：分类为 `editable`、`needs_template` 或 `conflict`
- `find_config_conflicts`：检查重复项和不可安全修改的结构
- `save_codex_config`：原位修改可编辑配置
- `create_custom_template_config`：自动创建稳定模板并保留认证信息
- `restore_default_config`：备份后删除两份配置文件
- `is_official_login_mode` / `set_official_login_mode`：持久化官方登录模式
- `CodexConfigApp.load_path`：启动和切换目录时的状态调度
- `CodexConfigApp.save_current`：普通保存或自动模板转换
- `CodexConfigApp.restore_defaults`：官方账号登录流程

## 界面约定

- 标题“Codex 配置助手 ⓘ”打开关于软件
- 关于软件显示版本、作者、邮箱和 GitHub 项目地址，并可重新打开新手引导
- 新手引导可选择“下次不再提示”
- 赞赏码位于主界面右上方，点击打开大图
- 赞赏弹窗只使用标题栏右上角关闭按钮，同时支持 `Enter` 和 `Esc`
- 主界面不提供手动“创建自定义模板”按钮

## 资源和打包

`赞赏.png` 是 Tkinter 和 PyInstaller 使用的运行资源，必须保留。`赞赏.jpg` 是原始图片，也应提交。

```bat
build.bat
```

或者：

```powershell
.\build.ps1
```

两个脚本都会把 `赞赏.png` 打入单文件程序。产物位于 `dist/CodexConfigTool.exe`，应发布到 GitHub Releases，不应提交到仓库。

`build.bat` 适合双击运行，会检查 Python、自动安装 PyInstaller、检查资源与 exe 占用，并在结束时暂停。自动化环境可设置 `CI=1` 跳过暂停。

## 验证清单

修改后至少检查：

1. `python -m py_compile codex_config_tool.py`
2. 完全无配置时自动创建模板，且不生成空备份
3. 官方最小配置在普通模式下自动备份并转换
4. 可编辑配置只修改 API Key、Provider 显示名称、Base URL 和 Model
5. 重复字段或复杂 Provider 结构被拒绝
6. 恢复默认后两份配置文件被删除，聊天目录和数据库仍存在
7. 关闭并重开应用后，官方登录模式仍有效
8. 官方登录模式下保存 API 配置后自动创建模板并退出该模式
9. 关于软件、新手引导和赞赏弹窗内容完整且无裁切
10. PyInstaller 打包成功并包含 `赞赏.png`

测试时应使用临时 `USERPROFILE`、`APPDATA`、`LOCALAPPDATA` 和 `CODEX_HOME`，避免读取或修改开发电脑上的真实 `.codex`。

## 已知边界

- TOML 处理器针对 Codex 当前配置结构实现，并不是完整 TOML 解析器
- 工具不联网，也不验证 API Key、Base URL 或模型是否真实可用
- 官方登录模式目前记录一个配置目录路径
- 仓库当前没有独立自动化测试套件，核心流程需要按上面的隔离测试矩阵验证
- 发布公开仓库前应由维护者选择并补充合适的 LICENSE

## 后续开发原则

修改前先阅读 README 和本文件。涉及配置分类、Provider ID、认证文件、恢复默认或备份行为的改动，应先在临时目录复现实验，再修改代码。完成后同步更新 README、HANDOFF 和版本号，并重新验证源码运行与 PyInstaller 打包。
