# 发布报告

## v1.5.0

- 版本：`1.5.0`
- 发布提交：`762da155f2f9aa686ad4c47c3e5c2a7b0d0f71dd`
- 标签：`v1.5.0`（annotated，`4c790ad1`），解引用后与发布提交一致
- GitHub Release：https://github.com/z1099530893/Codex_ConfigTool/releases/tag/v1.5.0（release id `392103053`）
- 源码归档：GitHub 自动生成的 ZIP/TAR.GZ 均由 `v1.5.0` 标签生成
- 便携版：`CodexConfigTool-Portable-v1.5.0.exe`，53,519,038 字节，SHA-256 `70c8448a0926d65a289761101d36a723c4414d662f6a73338c470b6240446399`
- 安装版：`CodexConfigTool-Setup-v1.5.0.exe`，54,956,911 字节，SHA-256 `92a43ce0af0d29a4eed31b58051206c79884a4e775bbe19f5063ba04afe134a7`
- 前端：只有 Qt（PySide6）。**Tk 版自本版起不再发布**，但其视图层保留在 `codex_config_tool.py` 中——`codex_config_qt.py` 通过 `import codex_config_tool as core` 把它当业务逻辑库使用，删除即导致发布的前端无法启动。
- 验证：Python 3.13.9 语法检查；**127 项标准库测试**；PyInstaller 6.22.2 重建（47 秒）；Inno Setup 6.7.1 编译；打包启动 **8/8**；恢复闪烁复测 8 轮 `blank 0` / `native_descendants 0`；`DestName` 改名语义用一个一次性安装器实测确认。
- 上传后核对：发布页正文与本地 `docs/RELEASE_NOTES_1.5.0.md` 逐字符一致（4,973 字符）；两个附件的字节数与 SHA-256 与本地一致（对照 GitHub 的 `digest` 字段）；`releases/latest` 指向 `v1.5.0`。
- 已知限制：**安装/升级路径未经端到端验证**——本机已装 v1.4.0，运行安装包会覆盖用户的实际安装，因此安装路径的结论来自编译期证据加 `DestName` 实测。真实 Codex 环境、任务栏、系统托盘与闪烁结论仍需用户复测。
- 授权：用户于 2026-09-19 要求整理源码、重新打包、整理完整问题清单、升到 `1.5.0` 并更新仓库与发布页；同日追加决定只保留 Qt 版。
- 保留对象：`v1.0.0` 至 `v1.4.0` 的标签、Release、说明和资产不变（上传后已核对：六个发布页的资产数量与发布时间均未变化）。
- 回滚信息：本版之前的远端提交 `993fd7f`；本地发布前快照 `backups/pre-1.5.0-release-20260919-202241/`。
- 相关记录：CR-009、BUG-004、BUG-005、DEV-044、DEV-045、TEST-008、TEST-009

## v1.4.0

- 版本：`1.4.0`
- 发布提交：`993fd7f8631bfcfe29b48d08528bf589dea8d805`
- 标签：`v1.4.0`，与发布提交一致
- GitHub Release：https://github.com/z1099530893/Codex_ConfigTool/releases/tag/v1.4.0
- 源码归档：GitHub 自动生成的 ZIP/TAR.GZ 均由 `v1.4.0` 标签生成
- 便携版：`CodexConfigTool-Portable-v1.4.0.exe`，13,538,969 字节，SHA-256 `A82178A70F12AE537BAE86F8F2D31048094040919E2B3D8F2FAD960C895E8DCE`
- 安装版：`CodexConfigTool-Setup-v1.4.0.exe`，15,304,391 字节，SHA-256 `C0D90482F360E8ED1A1B9BFDC634DDCD3B6B5E608E9FB71F9511A0D8D4AD37B5`
- 验证：Python 3.12.13 语法检查；118 项标准库测试；`git diff --check`；PyInstaller 6.20.0 干净构建；Inno Setup 6.7.3 编译；Windows 版本资源、JM2 资源和隔离启动验证
- 已知限制：真实 Codex A→B→A、任务栏和系统托盘行为仍需客户在实际环境复测
- 授权：客户于 2026-09-01 明确要求整理源码、提交 GitHub并重建现有 `v1.4.0` 发布包、标签和发布页
- 保留对象：`v1.0.0` 至 `v1.3.0` 的标签、Release、说明和资产不变
- 恢复信息：旧 `v1.4.0` 提交 `12b5086c11d40d1a7b70b0ffddedab59e6c834ec`；旧 Release ID `377653760`；旧资产 ID `533361707`、`533361556`
