# 项目状态

- 阶段：Release
- 当前节点：v1.5.0 正式发布
- 状态：**待用户复测**。四个发布资产已构建并通过打包启动、最小化/恢复循环和闪烁复测；BUG-004（系统托盘图标）与 BUG-005（窗口交互）的结论只能由用户在真实环境亲手确认。

## 本轮完成

- **新增 Qt（PySide6）前端** `codex_config_qt.py`，复用主程序全部业务逻辑，只重写视图层；消除 Tk 顶层窗口因缺少 backing store 导致的恢复闪烁（实测 Tk 8/8 闪、12/241 空白帧；Qt 0/8 闪、0/241 空白帧）。
- **修复无边框主窗口交互缺陷**：最小化后程序退出、任务栏图标点击无反应、配置切换后任务栏图标消失、拖动界面破碎、打包版尺寸递增、原生与自绘标题栏叠加、窗口可被最大化。修复过程中撤回了动态 Win32 边框/尺寸补偿和自定义 WndProc 方案（后者曾触发 Python GIL 崩溃），回到稳定的 Tk 无边框基线。
- **修复确认对话框「是/否」按钮左右颠倒**。Tk 的 `pack(side="right")` 与 Qt 的 `QHBoxLayout` 对「第一个」的定义相反，该差异适用于每一个右对齐按钮对。
- **五页版面全部对齐**，`worst |dy| = 0px`。
- **构建链路改为一次产出四个资产**（两种前端各自的便携版与安装版），并显式验证解释器。
- **修复 `.spec` 通配忽略规则**：此前 `CodexConfigTool-Qt.spec` 未被纳入版本控制，而 `build_qt.ps1` 依赖它，导致从新克隆的仓库无法构建 Qt 前端。
- 新增 `docs/ISSUE_LEDGER.md`（全部已知缺陷及其状态）与 `docs/RELEASE_NOTES_1.5.0.md`。

## 验证

- Python 3.13.9 语法检查、**124 项标准库测试**、PyInstaller 6.22.2 构建、Inno Setup 6 编译通过。
- 打包启动验证 **8/8**、最小化/恢复循环验证 **55/55**、闪烁复测 5 轮 `blank 0` / `native_descendants 0`。
- 打包版验收脚本（拖动、两条点击路径、任务栏按钮真实存在）**PASS 5/5**——此前三次均被宿主机的合成输入限制挡在注入之前。
- 未修改真实 `.codex`、API Key、聊天记录或用户配置。

## 正式产物

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `CodexConfigTool-Qt-Setup-v1.5.0.exe` | 54,956,689 字节 | `cdf37d87833431afcfd67ab2e14fa23581e991c7ebab9a829baa05478c8c3599` |
| `CodexConfigTool-Qt-Portable-v1.5.0.exe` | 53,519,111 字节 | `3e6b85c5be2b438262705df45b59b56881bc144771e2d3fd6c568f2c4919c244` |
| `CodexConfigTool-Setup-v1.5.0.exe` | 14,961,160 字节 | `572417dbe15baef7f1adffd932620c5112a6e72f92f55f0e0170924188239a25` |
| `CodexConfigTool-Portable-v1.5.0.exe` | 13,165,940 字节 | `b3f5e179d7d46f9a55d4d07921c341ca6aedf6f9226f61e92d3d4a0ef2f715d9` |

## 下一步

- **用户在本机亲眼确认**：Qt 版恢复窗口时确实不再闪烁；主窗口尺寸、拖动、最小化、任务栏点击切换、关闭行为。
- 用户在真实 Codex 环境复测 BUG-004 的系统托盘图标与托盘右键退出。
- 确认侧栏选中色块应在最左还是最右（Tk 的实际行为是最左，移植版跟的是 Tk）。
- 在空闲机器上重跑 `verify_qt_app.py`，以及对 v1.5.0 Qt 产物重跑打包版验收脚本。

## Git

- 本地 `git init` 并提交，打 `v1.5.0` 标签；推送由用户执行。
- `v1.0.0` 至 `v1.4.0` 保持不变。

## 相关记录

- 缺陷台账：`docs/ISSUE_LEDGER.md`
- 发布说明：`docs/RELEASE_NOTES_1.5.0.md`
- 窗口问题完整调查：`AGENT_HANDOFF_WINDOW_BUGS.md`
- 测量工具：`prototypes/README.md`
- 变更请求与开发日志：`CR-001`～`CR-008`、`BUG-004`、`BUG-005`、`DEV-031`～`DEV-044`、`TEST-007`、`TEST-008`
