# 开发记录

## DEV-011 - 2026-08-28 - 更新提示改为关于图标红点

阶段和模式：Development
相关 ID：CR-004、TEST-004
客户确认：保留自动检查更新，不自动下载；发现新版本时使用“关于软件”图标右上角的小红点提示。
工作内容：新增关于图标红点状态；检测到新版本时不再弹窗，关于窗口直接显示版本提示并将按钮切换为“前往下载”；检查确认已是最新版本时恢复默认图标状态。
验证证据：Python 语法检查通过；68 项标准库测试通过；`git diff --check` 通过。
结果：更新检查仍为后台/手动检查，下载动作仍由用户主动触发。
待处理 Git 操作：无授权，不提交。

## DEV-010 - 2026-08-28 - 卸载器用户数据范围收紧

阶段和模式：Development
相关 ID：CR-005、P-005C、TEST-005
客户确认：卸载器必须由本项目执行删除，提供“保留用户数据”和“完全删除用户数据”两个互斥选项；不得调用第三方卸载工具或触碰 Codex 用户数据。
工作内容：修正 Inno Setup 自定义卸载窗口并完成真实编译；默认选中保留用户数据。完全删除仅清理 `%APPDATA%\\CodexConfigTool` 和 `%USERPROFILE%\\.codex\\backups`，不扫描、不删除 `%APPDATA%\\Codex`、`%LOCALAPPDATA%\\Codex` 或 `.codex` 根目录的其他内容。
保护范围：`auth.json`、`config.toml`、`sessions`、`archived_sessions`、`history.jsonl`、当前配置和聊天记录均不在删除目标内。
验证证据：Inno Setup 6.7.3 编译成功；Python 语法检查通过；68 项标准库测试通过；`git diff --check` 通过；已重新生成便携版和安装包。
结果：卸载器删除范围与用户确认一致，安装包产物可供隔离环境复测。
待处理 Git 操作：无授权，不提交。

## DEV-009 - 2026-08-28 - 安装界面与卸载数据保护修正

阶段和模式：Development
相关 ID：CR-005、P-005C、TEST-005
客户反馈：安装目录浏览界面仍有英文；桌面快捷方式显示 `(D)`；1.4.0 主程序出现双标题栏；卸载时没有保留/删除数据的选择；需要警告第三方卸载工具误删 Codex 目录。
工作内容：补充安装器磁盘空间和快捷方式中文消息，移除桌面快捷方式助记键；修复主程序任务栏注册重新加入 `WS_CAPTION` 导致原生标题栏与自绘标题栏叠加的问题；卸载器增加确认流程，仅允许删除 `%APPDATA%\\CodexConfigTool`，不会删除 Codex 配置、API Key、配置库或聊天记录；README 与 HANDOFF 增加第三方卸载工具误删 `%APPDATA%\\Codex`、`%LOCALAPPDATA%\\Codex` 的警告。
验证证据：Python 语法检查通过；68 项标准库测试通过；Inno Setup 6.7.3 真实编译成功；安装器脚本编译接受卸载确认代码；此前隔离安装、覆盖安装和卸载清理测试通过。
结果：修正版便携版和安装包已重新生成；待客户确认安装界面无英文残留、主程序仅显示单一标题栏，并实际点击卸载确认“保留/删除配置助手设置”两条路径。
待处理 Git 操作：无授权，不提交。
下一步：客户复测修正版安装包；安装目录浏览器仍使用 Windows 系统文件夹选择器，其系统语言由 Windows 自身决定。

## DEV-008 - 2026-08-28 - Windows 安装包和双产物构建

阶段和模式：Development
相关 ID：CR-005、P-005A、P-005B、P-005C、TEST-005
客户确认：采用当前用户安装的 Windows 安装包；桌面快捷方式默认勾选但可在安装时取消；继续保留便携版。
工作内容：新增 `packaging/CodexConfigTool.iss` 和项目内简体中文消息覆盖；新增 `scripts/build_installer.ps1` 与 `scripts/build_installer.bat`，从当前 PyInstaller 单文件构建版本化便携版和 Inno Setup 安装包；安装目录固定为 `%LOCALAPPDATA%\\Programs\\CodexConfigTool`，不要求管理员权限，提供开始菜单和卸载入口。
数据边界：安装器只打包 `CodexConfigTool.exe`，不包含、不迁移、不删除 `.codex`、`auth.json`、`config.toml`、会话目录或历史记录。
验证证据：Python 语法检查通过；66 项标准库测试通过；Inno Setup 6.7.3 真实编译成功；便携版 SHA256 为 `2bc386df61c7df862ecbdaa1903711bc3dd6bdc72fbb241c75d0d5b419878cdb`；安装包 SHA256 为 `992d65956e658131725aeb88ecce603aeb354611285278382ad5e525a61c3e8f`；隔离环境首次安装、默认/取消桌面快捷方式、同版本覆盖安装及卸载清理均通过。
结果：P-005A、P-005B 完成，P-005C 进入客户复测；P-005D（一键下载、校验并启动安装器）暂未实现。
待处理 Git 操作：无授权，不提交。
下一步：客户安装测试包进行实际验收，重点确认现有 Codex 配置、API Key 和聊天记录不受影响。

## DEV-007 - 2026-08-28 - Codex 重启图标修复通过真实环境验收

阶段和模式：Development
相关 ID：BUG-004、TEST-004、P-004B
客户反馈：客户使用最新单文件构建，通过配置助手重启 Codex 并手动测试通过。
验收环境：Windows 上实际安装的 Codex 与打包版 Codex 配置助手；构建产物为 `dist/CodexConfigTool.exe`，SHA256 为 `2bc386df61c7df862ecbdaa1903711bc3dd6bdc72fbb241c75d0d5b419878cdb`。
验收结果：Codex 主窗口正常出现，Windows 任务栏图标和系统托盘 Codex 图标正常恢复，托盘退出入口可用；重启流程不再产生只能通过任务管理器结束进程的问题。
技术证据：此前 Python 语法检查、62 项自动测试、`git diff --check` 和 PyInstaller 单文件构建均已通过；本次补齐真实用户交互验收。
结果：BUG-004 状态更新为 ACCEPTED，P-004B 状态更新为 DONE，重启缺陷验收结论为 GO。
待处理 Git 操作：无授权，不提交。
下一步：实际复测“关于软件 → 检查更新”，完成 P-004C 集成验收。

## DEV-006 - 2026-08-28 - Codex 系统托盘重启修复返工

阶段和模式：Development
相关 ID：BUG-004、TEST-004
客户反馈：重启后 Codex 主窗口和任务栏入口出现，但系统托盘没有 Codex 图标，无法通过托盘菜单简单退出；截图中的橙色图标是 Clash，并非 Codex。
基线：上一轮直接使用 `IApplicationActivationManager` 激活 Store 应用，技术测试只验证了主窗口，没有验证托盘。
诊断证据：OpenAI 官方更新说明确认 Windows Codex 提供系统托盘菜单；已安装 Codex 主进程代码在 Windows 启动时无条件初始化固定 GUID 的 Electron Tray，失败时只记录错误并继续显示窗口；本机进程树显示 COM 激活后的 Codex 主进程属于配置助手子进程，单独结束配置助手后 Codex 桌面宿主也随之退出。
工作内容：重启时新增同一安装主进程的完全退出检查，残留时停止重启；旧实例退出后等待 3 秒供 Explorer 清理固定托盘 GUID；Store 版改由 `explorer.exe` + AppsFolder AUMID 交给 Windows Shell 独立启动；移除不再使用的 COM 激活实现。
集成结果：普通桌面版直接启动逻辑保持不变；未修改用户配置、API Key、聊天或会话数据。
验证证据：Python 语法检查通过；62 项测试通过；`git diff --check` 通过；PyInstaller 单文件构建成功，新版配置助手已启动。
结果：实现完成，待客户真实重启后确认系统托盘 Codex 图标及右键退出菜单。
待处理 Git 操作：无授权，不提交。
下一步：客户在新版配置助手点击“一键重启”，确认主窗口、任务栏和系统托盘均恢复。

## DEV-005 - 2026-08-28 - 更新检查 HTTP 403 修复

阶段和模式：Development
相关 ID：CR-004、TEST-004
客户反馈：配置助手窗口与任务栏入口已经出现，但“关于软件”中的手动更新检查返回 HTTP 403。
基线：窗口和任务栏注册修复已通过客户实际观察；更新检测仍调用匿名 GitHub REST API，可能触发限流。
工作内容：改为向 GitHub `/releases/latest` 发送 `HEAD` 请求并禁止自动跳转，只读取 302 `Location` 中的语义版本；不下载完整发布页，保留超时、地址校验和启动失败降级。
集成结果：关于页手动检查和启动后台检查继续共用同一检测函数；不修改用户配置、API Key、会话数据或系统权限。
验证证据：Python 语法检查通过；60 项测试通过；`git diff --check` 通过；GitHub 曾实机返回指向 `v1.4.0` 的 302；PyInstaller 单文件构建成功，新包已启动并显示“Codex 配置助手”窗口标题。后续一次 GitHub 请求发生网络连接超时，程序失败降级路径仍需客户实际复测。
结果：403 实现修复完成，状态为待客户复测。
待处理 Git 操作：无授权，不提交。
下一步：客户点击“关于软件 → 检查更新”，确认显示当前版本或在网络不可用时显示连接失败，而不是 HTTP 403；之后再验证真实 Codex 重启图标。

## DEV-004 - 2026-08-28 - 自动更新与 Codex 重启图标修复

阶段和模式：Development
相关 ID：CR-004、BUG-004、TEST-004
客户确认：启动后台检查 GitHub Release；关于页支持手动检查；只提示并打开下载页，不自动替换 EXE；修复一键重启后 Windows 右下角图标消失。
工作内容：新增有超时和响应上限的 GitHub Release 检测、语义版本比较、启动静默检查和关于页手动入口；Store 版 Codex 从 `explorer.exe shell:AppsFolder` 改为 `IApplicationActivationManager` 系统激活，普通桌面版保持直接启动。
验证证据：Python 语法检查通过；59 项测试通过；Windows 应用激活接口错误路径实机验证通过；PyInstaller 单文件构建并启动成功；GitHub 最新 Release 接口实机可访问。
结果：自动化验证完成，待客户用已启动的打包版检查关于页并执行一次真实 Codex 重启，确认任务栏/托盘图标。
待处理 Git 操作：无授权，不提交。

## DEV-003 - 2026-08-27 - 权限配置安全与敏感信息保护

阶段和模式：Development
相关 ID：CR-003、TEST-003
客户确认：保留配置安全校验、信任项目路径一致性检查和敏感信息保护；取消备份专属脱敏需求；不得影响模型列表读取。
工作内容：新增 TOML 语法和权限字段组合校验；统一配置目录规范绝对路径；模型列表网络错误统一隐藏已知 API Key；未改变实际 Authorization 请求头。
验证证据：`python -m py_compile codex_config_tool.py`；`python -m unittest discover -s tests -q`，55 项通过；PyInstaller 单文件构建通过，包内已确认包含 `assets/arkapi.png`。
结果：实现和自动化验证完成，待客户实际使用验证。
待处理 Git 操作：无授权，不提交。

## DEV-002 - 2026-08-27 - 非破坏性认证与 Provider 切换

阶段和模式：Development
相关 ID：CR-002、TEST-002
客户确认：API-A 切换官方登录再切回 API-K 时，聊天记录和会话不能丢失。
工作内容：将 `restore_backup` 改为字段级应用；官方登录只移除 `OPENAI_API_KEY` 并设置官方 Provider；保留核心文件、令牌、会话和未知字段；补充往返与失败回滚测试；更新用户文档。
验证证据：49 项标准库测试通过。
结果：实现完成，待构建和隔离运行验证。
待处理 Git 操作：无授权，不提交。
