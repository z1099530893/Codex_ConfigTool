# Codex 配置助手

Codex 配置助手是一个 Windows 桌面小工具，用来安全修改 Codex 配置目录中的 `auth.json` 和 `config.toml`。它可以修改 API Key、Provider 显示名称、Base URL 和 Model，并尽量避免改变 Codex 桌面端的本地状态。

程序使用 Python 标准库和 Tkinter 编写，可通过 PyInstaller 打包为单文件 `.exe`。

后续开发者或新的 Codex 会话请先阅读 [HANDOFF.md](HANDOFF.md)，其中记录了当前配置状态机、安全约束、关键函数和验证流程。

## 功能

- 自动识别常见 Codex 配置目录，例如 `%USERPROFILE%\.codex`
- 支持手动选择 Codex 配置目录
- 支持扫描常见位置
- 自动读取当前 `auth.json` 和 `config.toml`
- 缺少可编辑自定义 Provider 时，在完成命名备份后创建模板
- 支持修改 `auth.json` 中的 `OPENAI_API_KEY`
- 支持修改当前 Provider 段里的 `name`
- 支持修改当前 Provider 段里的 `base_url`
- 支持修改顶层 `model`
- 保存前要求为原始 `auth.json` 和 `config.toml` 命名备份
- 保存时可按当前状态自动创建自定义 API 配置
- 支持在“备份设置”中重命名、删除、批量删除和恢复备份
- 备份永久保留，不设数量上限，也不会被自动删除
- 支持恢复默认配置
- 点击标题旁的 `ⓘ` 打开关于软件
- 主界面显示赞赏码缩略图，点击可放大查看
- 首次启动时自动显示一次新手引导，之后可从主界面手动打开

## 界面

主界面提供配置目录选择、API Key、Provider 显示名称、Base URL 和 Model 输入框，以及以下操作：

- 重新读取
- 备份设置
- 打开备份目录
- 恢复默认配置
- 新手引导
- 保存配置

按钮使用紧凑的系统 `ttk.Button` 样式，适配当前窗口宽度。

标题显示为“Codex 配置助手 ⓘ”，整个标题区域可以点击，用于打开关于软件弹窗。

标题区右侧显示赞赏码缩略图，点击后会打开大图弹窗，方便扫码。赞赏功能与配置读写完全独立。

## 关于软件

点击主界面的“Codex 配置助手 ⓘ”标题可以打开关于软件弹窗。弹窗包含：

- 软件名称：Codex 配置助手
- 版本：1.1.0
- 软件用途简介
- 作者：k.x
- 联系邮箱：1099530893@qq.com
- 项目地址：https://github.com/z1099530893/Codex_ConfigTool
- Copyright 信息

点击邮箱可以复制到剪贴板；点击项目地址可以在默认浏览器中打开 GitHub 仓库。关于窗口不设置额外操作按钮，可使用标题栏 `×`、`Enter` 或 `Esc` 关闭。

## 新手引导

软件首次启动并完成配置检查后，会自动显示一次三步新手引导：

1. 填写服务商提供的 API Key、Base URL 和 Model，Provider 显示名称填写服务商名称
2. 点击“保存配置”，按提示为当前配置命名备份
3. 完全退出并重新打开 Codex，使新配置生效

关闭引导时，已显示状态会保存在 `%APPDATA%\CodexConfigTool\settings.json`，不会写入 Codex 的 `config.toml`，以后启动不再自动弹出。主界面的“新手引导”按钮始终可以手动重新打开引导；引导窗口可使用标题栏 `×`、`Enter` 或 `Esc` 关闭。

## 安全保存逻辑

对已有可编辑自定义配置的普通保存，会先读取顶层：

```toml
model_provider = "newapi"
```

然后定位对应的 Provider 段：

```toml
[model_providers.newapi]
name = "openai"
base_url = "https://example.com/v1"
```

这种普通保存只修改：

- `auth.json` 里的 `OPENAI_API_KEY`
- 当前 Provider 段里的 `name`
- 当前 Provider 段里的 `base_url`
- 顶层 `model`

这种普通保存不会修改：

- 顶层 `model_provider`
- `[model_providers.xxx]` 段名
- `model_reasoning_effort`
- `disable_response_storage`
- `preferred_auth_method`
- `[features]`
- `[desktop]`
- `[marketplaces...]`
- `[plugins...]`
- `[mcp_servers...]`
- `[windows]`
- `[projects...]`

这样设计是为了避免改变 Codex 桌面端的本地状态上下文，减少聊天窗口被重置或隐藏的风险。

实验结论：导致聊天记录窗口丢失或隐藏的高风险操作，是改动 `model_provider` 的 Provider ID，以及对应的 `[model_providers.xxx]` 段名。也就是说，不要把：

```toml
model_provider = "newapi"
[model_providers.newapi]
```

改成另一组 ID，例如：

```toml
model_provider = "otherapi"
[model_providers.otherapi]
```

普通保存因此只修改 Provider 段内部的 `name`、`base_url` 和顶层 `model`，不重命名 Provider ID。当前配置无法直接编辑时，“保存配置”会先要求为现有配置命名备份，再自动创建稳定的自定义模板；这属于初始化转换，不会猜测或重命名已有自定义 Provider。

如果当前配置是干净的内置 `openai` 默认状态，软件启动时会先完成命名备份，再创建可编辑模板。取消命名时不会修改原配置。复杂或冲突配置不会被自动覆盖。

## 自动初始化

软件启动或切换配置目录时会自动检查 `auth.json` 和 `config.toml`：

- 已有有效自定义 Provider：直接读取并进入主界面，不修改文件
- 两个配置文件都不存在：视为首次使用，创建配置目录、空的 `auth.json` 和可编辑的 `config.toml`，不创建空备份
- 只缺少 `config.toml`：要求命名或复用已有备份，保留 `auth.json` 后再创建模板
- 当前是干净的官方 `openai` 默认配置：要求命名或复用已有备份，再创建模板
- 用户主动执行“恢复默认配置”后：进入官方登录模式，保留 Codex 自己生成的配置，不自动创建模板
- 存在重复字段、多个冲突 Provider 段或其它复杂结构：停止自动处理并显示错误

自动初始化会重写需要转换的 `config.toml`。如果 `auth.json` 已存在，会完整保留其中的登录和认证字段；如果不存在，才创建空的 `auth.json`。

首次完全没有配置时，状态栏会显示“检测到首次使用，已创建可编辑配置”。存在旧文件并发生自动转换时，用户需要确认备份名称；取消后原文件保持不变。

官方登录模式记录在工具自己的 `%APPDATA%\CodexConfigTool\settings.json` 中。软件关闭或电脑重启后仍然有效，直到用户填写 API 配置并点击“保存配置”，或恢复一个可编辑的自定义配置。

## 自动创建自定义模板

主界面不再提供手动“创建自定义模板”按钮。首次初始化或当前配置无法直接编辑时，软件会在启动或用户点击“保存配置”后创建模板。存在旧文件时会先命名或复用备份；没有旧文件时直接创建，不弹命名窗口，也不生成空备份。

模板会生成：

```toml
model_provider = "newapi"
model = "gpt-5.4"
model_reasoning_effort = "high"
disable_response_storage = true

[model_providers.newapi]
name = "openai"
base_url = "https://api.openai.com/v1"
wire_api = "responses"
requires_openai_auth = true

[features]
multi_agent = true
```

创建模板后建议重新打开 Codex，让 Codex 自动补全 `[desktop]`、`[marketplaces...]`、`[windows]`、`[projects...]` 等桌面端状态。后续再使用普通保存修改 API Key、Provider 显示名称、Base URL 和 Model。

不要手动或通过普通保存修改：

```toml
model_provider = "newapi"
[model_providers.newapi]
```

这两个值会被保留为稳定的 Provider ID。

## 恢复默认配置

“恢复默认配置”用于准备登录自己的 ChatGPT/GPT 账号。确认后，软件会：

1. 命名或复用当前 `auth.json` 和 `config.toml` 的备份
2. 删除这两个配置文件
3. 保留聊天记录、本地数据库、日志和已有备份
4. 进入持久化的官方登录模式
5. 提示用户关闭本工具并启动 Codex，按照 Codex 的提示登录

软件不会生成替代的 `auth.json` 或 `config.toml`，而是由 Codex 自己创建当前版本需要的官方配置。官方登录模式下再次打开本工具，也不会自动覆盖这些官方配置。以后填写 API 配置并点击“保存配置”时，软件会要求命名或复用备份并创建自定义模板，同时退出官方登录模式。

## 备份和恢复

备份目录位于当前 Codex 配置目录下：

```text
backups/
```

每个备份是一个独立文件夹，名称格式为：

```text
yyyyMMdd-HHmmss-备份名称/
```

备份文件夹中会保存：

```text
auth.json
config.toml
```

备份没有数量上限，也不会被软件自动删除。用户可以通过主界面的“备份设置”查看名称和创建时间，并使用右键菜单编辑名称、删除单个备份或进入多选删除模式。

以下操作在存在旧配置时都必须先命名或复用备份；取消命名会取消整个操作：

- 保存配置
- 自动创建自定义模板
- 恢复默认配置
- 恢复历史备份前的当前配置

备份名称默认取磁盘上真正被备份配置的 Provider 显示名。名称不区分大小写且必须唯一；如果同名备份的 Provider ID、显示名、Base URL、Model 和 API Key 都与当前配置相同，软件会直接复用该备份。Codex 自动写入的其它桌面状态不会造成重复备份。同名但核心配置不同则必须使用新名称。

“备份设置”中的备份按时间从新到旧排列。“恢复选中备份”只支持单选；进入多选模式后可以直接点击条目切换选择、按住鼠标左键连续拖选，或使用“全选/取消全选”和 `Ctrl+A`。通过“删除所选备份”可以批量删除，所有删除操作都需要二次确认。

## 从源码运行

开发环境需要：

- Windows
- Python 3.10 或更高版本

运行：

```powershell
python codex_config_tool.py
```

本项目只使用 Python 标准库，不需要安装额外运行依赖。

## 开发交接

项目当前实现决策、关键代码入口、官方登录模式、测试矩阵和后续开发注意事项统一记录在 [HANDOFF.md](HANDOFF.md)。修改配置状态机、备份行为或 Provider 定位逻辑时，应同步更新 README 和交接文件。

## 打包为 exe

可以直接运行：

```bat
build.bat
```

可以直接双击 `build.bat`。脚本会显示 Python、PyInstaller、资源文件和程序占用检查结果；完成或失败后窗口会暂停，不会一闪而过。

如果没有安装 PyInstaller，脚本会自动执行：

```powershell
python -m pip install pyinstaller
```

然后继续打包。

打包前需要关闭正在运行的 `CodexConfigTool.exe`，否则 Windows 无法覆盖旧文件。

也可以运行 PowerShell 脚本：

```powershell
.\build.ps1
```

打包完成后，可执行文件位于：

```text
dist/CodexConfigTool.exe
```

建议 GitHub 仓库只提交源码和脚本，`.exe` 文件放到 GitHub Releases 中发布。

## 文件结构

```text
.
├── codex_config_tool.py   # 主程序源码，包含 Tkinter 界面、配置读取/保存、备份和恢复逻辑
├── build.bat              # Windows 批处理打包脚本；缺少 PyInstaller 时会自动安装
├── build.ps1              # Windows PowerShell 打包脚本
├── 赞赏.jpg               # 原始赞赏码图片
├── 赞赏.png               # 程序界面及打包使用的 PNG 图片
├── tests/                 # 使用临时目录验证备份与恢复逻辑的标准库测试
├── HANDOFF.md             # 开发交接、架构说明和验证清单
├── README.md              # 项目说明文档
└── .gitignore             # Git 忽略规则
```

本地开发时可能存在 `.git/` 目录，这是 Git 仓库元数据，不属于需要上传的项目文件。

打包或运行过程中可能出现的临时目录：

```text
build/
dist/
__pycache__/
*.spec
```

这些文件已经写入 `.gitignore`，不需要提交。

上传 GitHub 时只提交源码、文档、构建脚本和图片资源。`dist/` 中的 `.exe` 应作为 GitHub Release 附件发布，不应提交到源码仓库。

## 注意事项

- 保存和恢复前按提示确认备份名称；取消命名不会修改配置
- 备份不会自动删除，可在 `备份设置` 中手动管理
- 普通保存不会主动删除聊天记录文件
- 普通保存不会改 `model_provider` 和 Provider 段名
- 普通保存会修改顶层 `model`
- 修改配置后，通常需要重新打开 Codex 才能读取新配置
- 本工具不会联网，也不会上传、校验或保存 API Key 到远程服务
