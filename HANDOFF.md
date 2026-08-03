# Codex 配置助手开发交接

## 当前版本

- 版本：`1.2.0`
- 平台：Windows
- 技术栈：Python 标准库、Tkinter、PyInstaller
- 主程序：`codex_config_tool.py`
- 项目地址：https://github.com/z1099530893/Codex_ConfigTool

程序是一个固定窗口大小的 Codex 配置管理工具。当前产品概念是“配置切换”，不是历史备份恢复。

## 目录和数据

- 当前 Codex 配置目录由用户选择或自动识别，通常为 `%USERPROFILE%\.codex`
- 当前目录中的 `auth.json` 和 `config.toml` 是正在使用的配置
- 配置库位于当前目录的 `backups/`
- 每个配置目录格式为 `yyyyMMdd-HHmmss-名称`
- 配置库配置永久保留，无数量限制，不自动清理，不自动更新时间
- `%APPDATA%\CodexConfigTool\settings.json` 保存工具设置和官方登录模式

## 配置安全规则

普通保存只允许修改：

- `auth.json` 的 `OPENAI_API_KEY`
- 当前 Provider 段的 `name`、`base_url`
- 顶层 `model`

不得修改顶层 `model_provider`、`[model_providers.xxx]` 段名、聊天记录、SQLite 数据库、日志和 Codex 桌面状态。复杂、重复或无法唯一定位的 Provider 结构必须停止处理，不得猜测覆盖。

新增配置时，只有内容不匹配已有配置时才要求命名；同核心内容的配置直接复用。切换已有配置不弹命名、不保存离开的配置、不修改目标配置目录。

恢复官方登录只删除当前目录的 `auth.json` 和 `config.toml`，并保留其他文件和配置库。

## 代码入口

- `CodexConfigApp`：主窗口、页面、弹窗和用户交互
- `classify_config_for_editing`：判断配置是否可编辑、需要模板或存在冲突
- `read_codex_config` / `save_codex_config`：读取和原位保存当前配置
- `create_custom_template_config`：创建稳定的自定义 Provider 模板
- `build_backup_signature` / `build_requested_signature`：生成配置核心签名
- `find_matching_backup`：查找内容相同的配置库项目
- `create_named_backup` / `restore_backup`：创建和切换配置库项目
- `save_config_profile` / `update_config_profile`：保存新增配置和编辑配置
- `rename_backup` / `delete_backups`：重命名、单删和批量删除配置目录
- `restore_default_config`：进入官方登录模式前删除两份当前配置文件
- `acquire_single_instance` / `release_single_instance`：Windows 单实例互斥量
- `FlatVerticalScrollbar`：配置列表的扁平自绘滚动条

## 界面约定

- 主窗口固定为 `820 × 500`，无最大化按钮
- 自定义深色标题栏提供关于、最小化、关闭和窗口拖动
- 左侧页面顺序为当前配置、切换配置、官方登录、新手引导
- 当前页面只读；配置编辑统一从新增配置或切换配置页面进入
- 配置列表外围始终为浅灰细边框，选中只改变对应行背景
- 次要按钮使用统一浅灰背景，绿色按钮表示主要操作
- 瞬时消息使用无背景纯文字，位于右侧页面底部留白
- 眼睛按钮不显示悬停提示
- 首次启动的新手引导居中显示一次，之后只从导航页手动查看

## 单实例和退出

`main()` 在创建 Tk 窗口前获取 `Local\\z1099530893.CodexConfigTool` 互斥量。重复启动只显示提示，不读取或写入配置。关闭主窗口后 Tk 主循环退出，`finally` 释放互斥量；扫描线程使用 daemon，不阻止程序结束。

## 资源和打包

PyInstaller 必须包含：

```text
赞赏.png
app_icon.png
app_icon_title.png
app_icon_about.png
eye_smooth.png
eye_off_smooth.png
app_icon.ico
```

使用 `build.bat` 或 `build.ps1` 打包。`dist/`、`build/`、`*.spec`、`__pycache__/` 已加入 `.gitignore`，不提交到源码仓库。EXE 上传到 GitHub Releases。

## 验证清单

每次修改后执行：

1. `python -m py_compile codex_config_tool.py`
2. `python -m unittest discover -s tests -q`
3. 在临时 `APPDATA`、`CODEX_HOME` 下验证新增、编辑、切换、删除和官方登录
4. 验证取消保存不会修改任何配置文件
5. 验证超过 5 个配置仍全部保留
6. 验证列表选择、拖选、全选、滚动条和弹窗按钮的 Windows 界面效果
7. 关闭程序后确认进程结束，再进行 PyInstaller 打包

## 后续修改原则

保持配置解析、Provider ID、官方登录流程和 Codex 桌面状态保护不变。涉及配置文件写入时，必须先在临时目录验证；完成后同步更新 README、HANDOFF、CHANGELOG 和版本号，并运行完整测试。
