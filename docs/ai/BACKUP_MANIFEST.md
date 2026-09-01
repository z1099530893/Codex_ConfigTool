# 回滚副本清单

- 创建日期：2026-08-28
- 类型：仓库外文件级副本
- 路径：`%TEMP%\CodexConfigTool-model-switch-2026-08-28T16-51-27-706Z`
- 基线提交：`12b5086c11d40d1a7b70b0ffddedab59e6c834ec`
- 用途：保留本轮开始前已经存在的未提交修改，便于文件级人工恢复
- 包含：`codex_config_tool.py`、`tests/test_backup_management.py`、PROJECT/PLAN/CHANGE/DEVELOPMENT/ENVIRONMENT 等开发记录
- 不包含：真实 `.codex` 配置、API Key、聊天记录、构建产物、未知 `%SystemDrive%/` 目录
- 注意：该副本位于临时目录，不作为长期归档或 Git 提交内容；本轮没有自动恢复或删除它

## 2026-08-29 配置切换实机故障返工

- 类型：仓库外文件级副本
- 路径：`%TEMP%\CodexConfigTool-switch-order-2026-08-29T02-14-43-297Z`
- 用途：保留修复运行中配置切换顺序和推理强度目录前的工作区状态
- 包含：主程序、测试和相关 AI 开发记录
- 不包含：真实 `.codex` 配置、API Key、聊天记录、构建产物和未知 `%SystemDrive%/` 目录
- 注意：该副本位于临时目录；未自动恢复、删除或写入任何用户 Codex 配置

## 2026-08-29 Codex 原生模型元数据优先

- 类型：仓库外文件级副本
- 路径：`%TEMP%\CodexConfigTool-native-metadata-2026-08-29T02-36-44-300Z`
- 用途：保留接入 Codex 原生模型缓存和官方 Provider 目录清理前的工作区状态
- 包含：主程序、测试及相关 AI 开发记录
- 不包含：真实 `.codex`、API Key、聊天记录、构建产物和未知 `%SystemDrive%/` 目录
- 注意：该副本位于临时目录；本轮仅只读解析测试目录中的模拟缓存，未写入真实 Codex 配置

## 2026-08-30 安全重启流程

- 类型：仓库外文件级副本
- 路径：`%TEMP%\CodexConfigTool-safe-restart-2026-08-30`
- 用途：保留移除重启入口自动关闭和强制结束逻辑前的当前未提交工作区状态
- 包含：主程序、测试、交接文档及相关 AI 开发记录
- 不包含：真实 `.codex` 配置、API Key、聊天记录、构建产物和未知 `%SystemDrive%/` 目录
- 注意：该副本位于临时目录；未自动恢复、删除或写入任何用户 Codex 配置

## 2026-08-31 自动生命周期切换事务

- 类型：项目忽略目录文件级副本
- 路径：`build/rollback/dev026-profile-switch/`
- 用途：保留整合自动退出、配置同步、目标投影和启动事务前的主程序与测试
- 包含：`codex_config_tool.py`、`tests/test_backup_management.py`
- 不包含：真实 `.codex`、API Key、聊天记录、构建产物和未知 `%SystemDrive%/` 目录
- 注意：该目录被 Git 忽略，不进入源码提交或发布包；本轮未自动恢复或删除副本

## 2026-08-31 统一保存与双击应用事务

- 类型：项目忽略目录文件级副本
- 路径：`build/rollback/dev027-unified-profile-activation/`
- 用途：保留移除“保存并使用/保存并应用”、当前页模型编辑和引入待应用活动配置标记前的工作区状态
- 包含：`codex_config_tool.py`、`tests/test_backup_management.py`、`PROJECT_STATUS.md`、`PROJECT_PLAN.md`
- 不包含：真实 `.codex`、API Key、聊天记录、构建产物和未知 `%SystemDrive%/` 目录
- 注意：该目录被 Git 忽略，不进入源码提交或发布包；本轮未自动恢复、删除或写入任何用户 Codex 配置
