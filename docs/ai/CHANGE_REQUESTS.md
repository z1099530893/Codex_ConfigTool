# 变更请求

## CR-002 - 非破坏性切换认证模式

提出：2026-08-27
原始请求：API 配置、官方登录和新的 API 配置之间切换时，不丢失对话记录或配置。
状态：IN-PROGRESS
验收标准：不删除 `auth.json`、`config.toml`、`sessions/`、`archived_sessions/`、`history.jsonl`；保留令牌、账户和未知字段；API-A → 官方 → API-K 往返可用；写入失败时双文件回滚。
相关记录：DEV-002、TEST-002
