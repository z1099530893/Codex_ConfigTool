# 环境报告

- 日期：2026-09-01
- 项目接入：LOCAL-EXISTING
- OS 与架构：Windows 10.0.19044，x64
- 运行时与工具链：Python 3.12.13、PyInstaller 6.20.0、Inno Setup 6.7.3
- 依赖来源：项目运行仅使用 Python 标准库；沿用现有 PyInstaller 单文件打包链路
- 仓库：`main` 跟踪 `origin/main`；基线提交与 `v1.4.0` 为 `12b5086c11d40d1a7b70b0ffddedab59e6c834ec`
- 工作区：开始本轮时已有未提交源码、测试和开发文档修改，均按用户要求保留；未知 `%SystemDrive%/` 目录未触碰
- 回滚：已在仓库外创建文件级副本，位置记录于 `docs/ai/BACKUP_MANIFEST.md`
- 已检查：Git 状态与远端、Python、PyInstaller、现有构建定义、项目记录、受管文件范围和用户数据边界
- 打包结果：正式便携版与 Inno Setup 安装包从当前源码干净重建；便携版在隔离 `APPDATA`、`LOCALAPPDATA`、`USERPROFILE`、`CODEX_HOME` 启动 4 秒后仍正常运行，实际解包目录包含 `assets/jm2api.png`
- 警告：普通 PowerShell 终端入口受本机 Windows CET 错误影响；本轮使用同机 Node 子进程直接调用 Git/Python/PyInstaller 完成等价检查，不修改系统设置
- 环境变更：复用 Codex 工作区隔离 Python；未修改系统设置或真实 `.codex` 配置
- 结论：READY-WITH-WARNINGS
- 下一步：发布 `v1.4.0` 后继续由客户复测真实 Codex 工作流
