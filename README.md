# Codex 配置助手

Codex 配置助手 `1.2.0` 是一个 Windows 桌面工具，用于管理和切换多个 Codex 配置。程序使用 Python 标准库、Tkinter 和 PyInstaller，不联网，也不会上传 API Key。

## 功能

- 自动识别、手动选择或扫描 Codex 配置目录
- 读取和编辑 API Key、Provider 显示名称、Base URL 和 Model
- 新增配置并保存到配置库
- 在配置库中搜索、排序、切换、完整编辑、删除配置
- 支持右键菜单、全选、Ctrl+A 和鼠标左键拖选批量操作
- 配置永久保留，不设数量上限，不会自动删除或更新时间
- 当前配置只读展示，切换配置不弹出保存或确认窗口
- 官方登录模式和一次性新手引导
- Windows 单实例限制，避免多个窗口交叉修改配置
- 固定 `820 × 500` 窗口、扁平化界面、深色自定义标题栏

## 界面

左侧导航包含“当前配置”“切换配置”“官方登录”和“新手引导”。

“当前配置”页面显示当前配置名称、API Key、Provider 显示名称、Base URL 和 Model，并提供配置目录浏览与新增配置入口。API Key 默认隐藏，使用眼睛图标切换显示。

“切换配置”页面显示配置名称和 Base URL。当前配置使用绿色圆点标记；双击行的空白区域或点击切换按钮即可切换，名称和 Base URL 文本本身不会触发切换。列表滚动条为浅色扁平样式，选中时只改变对应行背景。

“官方登录”会在确认后删除当前目录中的 `auth.json` 和 `config.toml`，保留聊天记录、数据库、日志和配置库，然后由 Codex 在下次启动时完成官方登录。

## 配置库

配置库位于当前 Codex 目录的 `backups/` 子目录，每个配置使用以下目录格式：

```text
yyyyMMdd-HHmmss-配置名称/
```

目录中保存 `auth.json` 和 `config.toml`。配置名称不区分大小写且必须唯一。保存内容与已有配置核心内容一致时复用已有配置，不创建重复目录；切换配置只复制目标配置，不修改配置库内容和时间。

普通保存只修改以下字段：

- `auth.json` 中的 `OPENAI_API_KEY`
- 当前 Provider 段的 `name`
- 当前 Provider 段的 `base_url`
- 顶层 `model`

程序不会修改 `model_provider`、Provider 段名、聊天记录、SQLite 数据库或 Codex 桌面状态。无法安全识别的复杂配置会停止处理并提示用户。

## 新手引导

首次启动时在主窗口中央显示一次新手引导，说明“新增配置”和“切换配置”两个流程。关闭后记录在 `%APPDATA%\CodexConfigTool\settings.json`，以后不再自动弹出；左侧“新手引导”页面可随时查看。

## 运行

环境要求：Windows、Python 3.10 或更高版本。

```powershell
python codex_config_tool.py
```

本项目运行时只依赖 Python 标准库。

## 测试

```powershell
python -m py_compile codex_config_tool.py
python -m unittest discover -s tests -q
```

测试使用临时配置目录，不应读取或修改真实用户的 `.codex`。

## 打包

关闭正在运行的程序后执行：

```bat
build.bat
```

或：

```powershell
.\build.ps1
```

产物位于 `dist/CodexConfigTool.exe`。源码仓库只提交源码、文档、测试、构建脚本和图片资源；`.exe` 应作为 GitHub Release 附件发布，不提交到源码仓库。

## 文件结构

```text
codex_config_tool.py   主程序
tests/                 标准库测试
build.bat              Windows 批处理打包脚本
build.ps1              PowerShell 打包脚本
README.md              项目说明
HANDOFF.md             开发交接文档
CHANGELOG.md           当前版本变更摘要
赞赏.png               界面赞赏码
app_icon*.png/.ico     软件图标资源
eye_*_smooth.png       API Key 眼睛图标
```

## 联系

- 作者：k.x
- 邮箱：1099530893@qq.com
- 项目：https://github.com/z1099530893/Codex_ConfigTool
