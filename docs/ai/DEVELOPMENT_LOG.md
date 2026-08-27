# 开发记录

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
