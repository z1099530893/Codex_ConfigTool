# 项目状态

- 阶段：Release
- 当前节点：v1.5.0 正式发布（单前端）
- 状态：**待用户复测**。两个发布资产已构建并通过打包启动验证；BUG-004（系统托盘图标）与 BUG-005（窗口交互）的结论只能由用户在真实环境亲手确认。

## 本轮完成

- **界面换成 Qt（PySide6）前端** `codex_config_qt.py`，复用主程序全部业务逻辑，只重写视图层；消除 Tk 顶层窗口因缺少 backing store 导致的恢复闪烁（实测 Tk 8/8 闪、12/241 空白帧；Qt 0/8 闪、0/241 空白帧）。
- **自 1.5.0 起只发布 Qt 版**。Tk 的闪烁是结构性的、修不掉，把有缺陷的前端和修好的前端并排放进发布页，等于给用户一个选中坏版本的机会。Tk 视图层仍保留在 `codex_config_tool.py` 中且**不可删除**——`codex_config_qt.py` 通过 `import codex_config_tool as core` 把它当作业务逻辑库使用。
- **修复无边框主窗口交互缺陷**：最小化后程序退出、任务栏图标点击无反应、配置切换后任务栏图标消失、拖动界面破碎、打包版尺寸递增、原生与自绘标题栏叠加、窗口可被最大化。修复过程中撤回了动态 Win32 边框/尺寸补偿和自定义 WndProc 方案（后者曾触发 Python GIL 崩溃），回到稳定的无边框基线。
- **修复确认对话框「是/否」按钮左右颠倒**。Tk 的 `pack(side="right")` 与 Qt 的 `QHBoxLayout` 对「第一个」的定义相反，该差异适用于每一个右对齐按钮对。
- **五页版面全部对齐**，`worst |dy| = 0px`。
- **构建链路改为一次产出两个资产**（便携版 + 安装版，均来自 Qt 前端），并显式验证解释器；构建产物名与安装后名字拆成两个宏，由 `[Files]` 的 `DestName` 改名，使 `dist\` 里的 Qt 产物不与 Tk 回滚产物撞名，而安装后仍是 1.4.0 用户熟悉的 `CodexConfigTool.exe`。
- **修复 `.spec` 通配忽略规则**：此前 `CodexConfigTool-Qt.spec` 未被纳入版本控制，而 `build_qt.ps1` 依赖它，导致从新克隆的仓库无法构建 Qt 前端。
- 新增 `docs/ISSUE_LEDGER.md`（全部已知缺陷及其状态）与 `docs/RELEASE_NOTES_1.5.0.md`。

## 验证

- Python 3.13.9 语法检查、**127 项标准库测试**、PyInstaller 6.22.2 构建、Inno Setup 6.7.1 编译通过。
- 打包启动验证 **8/8**（窗口类 `Qt6112QWindowIcon`、`820x500`、无原生边框、0 原生子窗口、任务栏样式在位、隔离 APPDATA）。最小化/恢复循环验证 **55/55**；恢复闪烁复测在**本次构建的字节上**重跑 8 轮：`blank 0`、`native_descendants 0`、`sidebar settled 91.0 max 91.0`（报告 `prototypes/out/flash-qt-exe-v150-rebuilt.json`）。
- 打包版验收脚本（拖动、两条点击路径、任务栏按钮真实存在）**PASS 5/5**——此前三次均被宿主机的合成输入限制挡在注入之前。
- `DestName` 的改名语义用一个一次性安装器（独立 `AppId`、`Uninstallable=no`、装到临时目录）实测确认：`version_info.txt` 确实落成 `ProbeTarget.txt`，且未留下注册表项。
- **未修改真实 `.codex`、API Key、聊天记录或用户配置。**
- **未执行真正的安装步骤**：本机 `%LOCALAPPDATA%\Programs\CodexConfigTool` 已装有 v1.4.0，跑安装包会覆盖用户的实际安装。安装路径的验证是编译期证据（ISCC 成功压缩 `dist\CodexConfigTool-Qt.exe`）加 `DestName` 实测，不是端到端安装测试。

## 正式产物

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `CodexConfigTool-Setup-v1.5.0.exe` | 54,956,911 字节 | `92a43ce0af0d29a4eed31b58051206c79884a4e775bbe19f5063ba04afe134a7` |
| `CodexConfigTool-Portable-v1.5.0.exe` | 53,519,038 字节 | `70c8448a0926d65a289761101d36a723c4414d662f6a73338c470b6240446399` |

不发布的本地产物：`dist\CodexConfigTool-Qt.exe`（安装包的输入）、`dist\CodexConfigTool.exe`（Tk 回滚版，`b3f5e179…`，本轮未改动）。

## 下一步

- **用户在本机亲眼确认**：Qt 版恢复窗口时确实不再闪烁；主窗口尺寸、拖动、最小化、任务栏点击切换、关闭行为。
- 用户在真实 Codex 环境复测 BUG-004 的系统托盘图标与托盘右键退出。
- 确认侧栏选中色块应在最左还是最右（Tk 的实际行为是最左，移植版跟的是 Tk）。
- 在空闲机器上重跑 `verify_qt_app.py`，以及对 v1.5.0 Qt 产物重跑打包版验收脚本。
- 用 1.5.0 安装包覆盖本机已装的 1.4.0，确认升级路径（旧 EXE 被清掉、配置保留）。

## Git

- 仓库：`https://github.com/z1099530893/Codex_ConfigTool`（注意是下划线），默认分支 `main`。
- 本地已基于 `origin/main`（`993fd7f`）提交并打 `v1.5.0` 标签；推送由用户执行。
- `v1.0.0` 至 `v1.4.0` 保持不变。

## 相关记录

- 缺陷台账：`docs/ISSUE_LEDGER.md`
- 发布说明：`docs/RELEASE_NOTES_1.5.0.md`
- 窗口问题完整调查：`AGENT_HANDOFF_WINDOW_BUGS.md`
- 测量工具：`prototypes/README.md`
- 变更请求与开发日志：`CR-001`～`CR-008`、`BUG-004`、`BUG-005`、`DEV-031`～`DEV-044`、`TEST-007`、`TEST-008`
