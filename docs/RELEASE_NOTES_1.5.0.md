# Codex 配置助手 v1.5.0

本版本修复了无边框主窗口的一系列交互缺陷，并新增一个 **Qt 前端**，用于消除「从任务栏恢复窗口时闪一下」的问题。同一个版本提供两种前端，功能与界面完全一致，区别只在窗口渲染方式。安装版与便携版同时提供。

## 下载

两种前端共用同一个安装标识和安装目录，安装其中一个会替换另一个，**不会并存**。

| 文件 | 前端 | 说明 |
| --- | --- | --- |
| `CodexConfigTool-Qt-Setup-v1.5.0.exe` | Qt | **推荐**。修复了恢复窗口时的闪烁 |
| `CodexConfigTool-Qt-Portable-v1.5.0.exe` | Qt | 便携版，无需安装 |
| `CodexConfigTool-Setup-v1.5.0.exe` | Tk | 体积小，仍存在恢复时的闪烁 |
| `CodexConfigTool-Portable-v1.5.0.exe` | Tk | 便携版，无需安装 |

安装包按当前用户安装，支持开始菜单、可选桌面快捷方式和标准卸载流程。

## 新增与改进

### 新增 Qt 前端，消除恢复窗口时的闪烁

从任务栏恢复窗口时，Tk 前端的主界面会闪一下：顶层窗口先被呈现、内容后绘制，中间 1-3 帧由合成器用窗口自身的背景色填充。**这是 Tk 顶层窗口的结构性限制，不是可以修掉的 bug** —— 它没有 backing store。

已逐一排除的方案：

- 把整个视图压平到一个 `Canvas`：只改善约三分之一，仍然闪。
- `WS_EX_LAYERED`：不是变量，加了也一样闪。
- `WS_EX_COMPOSITED`：按**子窗口数**计费，118 个窗口 3 秒开销 0.3177 秒，不是解法。

缺的是**一个表面加一份 backing store**，只有 Qt 两者兼备。实测对比（同程序、同探针、各 8 轮）：

| 指标 | Tk 前端 | Qt 前端 |
| --- | ---: | ---: |
| 原生子窗口数 | 118 | 0 |
| 闪烁轮次 | 8/8 | **0/8** |
| 空白帧 | 12/241 | **0/241** |

Qt 前端复用 `codex_config_tool.py` 的全部业务逻辑（配置读写、配置库、进程处理、更新检查等），只重写视图层。完整的原因分析、测量方法与数据见仓库中的 `AGENT_HANDOFF_WINDOW_BUGS.md`，可复现的测量工具在 `prototypes/`。

体积明显大于 Tk 版，原因有两条，都不是可以省掉的：需要打包 Qt 运行时；而且 `codex_config_tool.py` 在模块顶层 `import tkinter`，Qt 前端把它整个当作库导入，所以连 tkinter 与 tcl/tk 也一并打包。这是「共用业务逻辑」这个架构的直接代价。

### 一次构建产出四个发布包

`scripts\build.bat` 现在是完整的发布入口，一次生成 Tk 与 Qt 的便携版和安装版共四个资产，并输出每个资产的字节数与 SHA-256。三个 PowerShell 脚本都会**显式验证解释器**（同时具备 tkinter、PySide6、PyInstaller），而不是信任 PATH 上的第一个 `python`——本机 PATH 上的那个没有 tkinter，构建不会报错，失败会推迟到运行期。

## 重要修复

### 无边框主窗口交互

- **修复点击最小化后配置助手自动退出**。此前在最小化/恢复时切换 `overrideredirect` 并重新注册任务栏样式，这会让 Windows Shell 重新创建任务栏按钮；现在主窗口在整个生命周期内保持无边框，最小化只对真实顶层 HWND 调用 Win32 `SW_MINIMIZE`。
- **修复任务栏图标点击无反应、关闭行为异常**。最小化此前用错窗口句柄（`winfo_id()` 而非它的顶层祖先）；另外 `PostMessageW` 未声明 64 位 HWND 参数类型，句柄被按 32 位整数截断，消息实际没有生效。两处均已修正。
- **修复配置切换重启 Codex 后助手任务栏图标消失**。恢复窗口时现在会在同一个顶层 HWND 上原地重新应用 `WS_EX_APPWINDOW`，不再通过 `withdraw/deiconify` 让 Explorer 重建按钮。
- **修复主窗口与任务栏图标只能同时存在一个**。隐藏原生边框时不再清除系统/最小化相关样式，保留 `WS_MINIMIZEBOX`、系统菜单和任务栏窗口样式。
- **修复拖动自绘窗口时界面破碎**。参考图像管理器的做法，拖动改为向同一个顶层 HWND 发送 `WM_NCLBUTTONDOWN/HTCAPTION`，不再在鼠标移动期间高频重设 Tk 几何尺寸。
- **修复打包版窗口尺寸递增和边界状态异常**。撤回了动态 Win32 边框/尺寸补偿和自定义 WndProc 方案（后者曾触发 Python GIL 崩溃），改为在初始化阶段抵消外框宽度偏差，窗口稳定为 `820×500`。
- **修复主界面同时显示 Windows 原生标题栏和自绘标题栏**。
- **主窗口不可最大化**。此前只移除 `WS_MAXIMIZEBOX` 并不阻止 `SC_MAXIMIZE`，现在有三道守卫；且守卫不会在最小化时误触发（此时窗口位于 `(-32000,-32000)`）。

### 界面细节

- **修复确认对话框的「是/否」按钮左右颠倒**。Tk 的 `pack(side="right")` 把先创建的控件放在最右，Qt 的 `QHBoxLayout` 从左往右追加，两个工具链对「第一个」的定义相反。该差异**适用于每一个右对齐按钮对**，读代码看不出来。
- 修正表格区域整体上移 9px：Tk 按 `linespace`、`QLabel` 按 `height()` 计算标签盒子高度，差在「每行」。症状是**邻居元素偏高**，不是「某个标签不对」。
- 修正 `panelHeading` 字号：角色未指定 `font-size` 时继承基础样式 9pt，而 Tk 用 8pt 粗体绘制。
- 修复自动换行文本被截断在句子中间：`QLabel.setWordWrap(True)` 在祖先面板为 `QSizePolicy.Fixed` 时只按 `sizeHint()` 给一行高度。

### 打包与安装

- **修复 Qt 安装包文件名缺少连字符**（`CodexConfigToolQt-Setup-…`）。
- **换前端安装时清理另一个前端的 EXE**。两个前端共用同一个安装标识和目录，新增 `[InstallDelete]` 段避免留下孤儿可执行文件。
- **`.spec` 被 `.gitignore` 忽略，但 Qt 构建脚本依赖它**。旧的 `*.spec` 通配规则会吞掉手工维护的 `CodexConfigTool-Qt.spec`，而 `build_qt.ps1` 在找不到它时直接报错——也就是说**从新克隆的仓库无法构建 Qt 前端**。现改为按名忽略历史预览 spec，两个正式 spec 纳入版本控制。

## 安装与数据安全

- 安装包默认安装到 `%LOCALAPPDATA%\Programs\CodexConfigTool`，不要求管理员权限。
- 覆盖安装不会删除 Codex 配置、API Key 或聊天记录。
- 卸载时默认「保留用户数据」。
- 选择「完全删除用户数据」时，仅删除 `%APPDATA%\CodexConfigTool` 和 `%USERPROFILE%\.codex\backups`。
- 卸载器不会扫描或删除 `%APPDATA%\Codex`、`%LOCALAPPDATA%\Codex`，也不会删除 `.codex` 根目录中的 `auth.json`、`config.toml`、`sessions`、`archived_sessions` 或 `history.jsonl`。
- 请勿使用第三方卸载工具清理 Codex 相关「残留」，以免误删 Codex 自身目录。

## 使用说明

完整功能介绍、全部界面截图、数据边界和已知问题请查看项目 [README](https://github.com/z1099530893/Codex_ConfigTool#readme) 与 [问题台账](https://github.com/z1099530893/Codex_ConfigTool/blob/main/docs/ISSUE_LEDGER.md)。

两种前端的使用方式完全相同，配置与设置也共用同一份，可以随时换用另一个前端而不影响已有配置。

## 文件校验

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `CodexConfigTool-Qt-Setup-v1.5.0.exe` | 54,956,689 字节 | `cdf37d87833431afcfd67ab2e14fa23581e991c7ebab9a829baa05478c8c3599` |
| `CodexConfigTool-Qt-Portable-v1.5.0.exe` | 53,519,111 字节 | `3e6b85c5be2b438262705df45b59b56881bc144771e2d3fd6c568f2c4919c244` |
| `CodexConfigTool-Setup-v1.5.0.exe` | 14,961,160 字节 | `572417dbe15baef7f1adffd932620c5112a6e72f92f55f0e0170924188239a25` |
| `CodexConfigTool-Portable-v1.5.0.exe` | 13,165,940 字节 | `b3f5e179d7d46f9a55d4d07921c341ca6aedf6f9226f61e92d3d4a0ef2f715d9` |

验证环境：Windows、Python 3.13.9、PySide6 6.11.2、PyInstaller 6.22.2、Inno Setup 6。Python 语法检查、124 项自动化测试、四个资产的构建与打包启动验证、隔离启动冒烟和闪烁复测均通过。

## 已知问题

- **Tk 前端仍存在恢复窗口时的闪烁**，这是 Tk 顶层窗口的结构性限制，无法在本项目范围内消除。请使用 Qt 前端。
- 与 Tk 版相比有 5 处像素级差异无法表达，均已量化并记录在问题台账的「已知未修」一节，例如表头的 1px 高光/阴影和列分隔线的双色描边。
- BUG-004（重启 Codex 后系统托盘图标偶发缺失）的修复流程已重做，仍需在真实 Codex 环境确认。
