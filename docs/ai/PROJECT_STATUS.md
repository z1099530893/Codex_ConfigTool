# 项目状态

- 阶段：Release
- 当前节点：v1.4.0 正式发布
- 状态：GO；源码、文档、截图和两个正式产物已验证，`v1.4.0` 以本提交作为发布源
- 已完成：当前配置页模型只读；新增/编辑仅单一保存并原子持久化完整模型列表；活动配置编辑使用待应用标记；双击配置统一应用、启动和自动重启；API/官方/API 往返不删除会话或聊天记录；8 张 README 正式截图已更新并对连接信息脱敏
- 本轮修复：双击当前配置在 Codex 停止时可启动；待应用副本不会被旧 live 配置反向覆盖；运行且无修改时不重复重启；事务失败恢复 live、配置库、活动和待应用标记；新增/编辑提示合并到按钮行并明确 OpenAI 原生模型无需获取列表；推荐渠道新增 JM2 API
- 验证：Python 3.12.13 语法检查、118 项标准库测试、`git diff --check`、PyInstaller 6.20.0 干净单文件构建、Inno Setup 6.7.3 编译、Windows 版本资源、JM2 打包资源及隔离启动通过；未修改真实 `.codex`、API Key 或聊天数据
- 正式产物：`dist/CodexConfigTool-Portable-v1.4.0.exe`（13,538,969 字节，SHA-256 `A82178A70F12AE537BAE86F8F2D31048094040919E2B3D8F2FAD960C895E8DCE`）；`dist/CodexConfigTool-Setup-v1.4.0.exe`（15,304,391 字节，SHA-256 `C0D90482F360E8ED1A1B9BFDC634DDCD3B6B5E608E9FB71F9511A0D8D4AD37B5`）
- 下一步：客户复测双击当前配置启动、活动配置待应用、A→B→A 自动生命周期、聊天保留、任务栏和系统托盘
- Git：本提交快进推送到 `origin/main`，并作为重建后的 `v1.4.0` 标签与 Release 源码
- 相关记录：CR-006、CR-007、CR-008、BUG-004、P-006J、P-007A、P-007B、P-007C、DEV-031、DEV-032、DEV-033、DEV-034、TEST-006、TEST-007
