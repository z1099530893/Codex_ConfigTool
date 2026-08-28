# Codex 配置助手开发交接

## 当前版本

- 版本：`1.4.0`
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
- 删除配置库项目不会修改当前目录的 `auth.json` 和 `config.toml`；匹配项被删除后当前状态显示为“未保存配置”

## 配置安全规则

普通保存只允许修改：

- `auth.json` 的 `OPENAI_API_KEY`
- 当前 Provider 段的 `name`、`base_url`
- 顶层 `model`

普通编辑不得修改顶层 `model_provider`、`[model_providers.xxx]` 段名、聊天记录、SQLite 数据库、日志和未涉及的 Codex 桌面状态。新增配置会先复制当前 `auth.json` 和 `config.toml`，只更新连接参数；当前配置是内置 openai 且需要自定义 Provider 时，会保留原内容并添加新的 Provider 段。复杂、重复或无法唯一定位的 Provider 结构必须停止处理，不得猜测覆盖。

新增配置时，只有内容不匹配已有配置时才要求命名；同核心内容的配置直接复用。新增配置的“保存”不改变当前配置；“保存并使用”会把基于当前文件修改后的配置写回当前目录，但不触碰聊天记录、数据库或日志。切换已有配置不弹命名、不保存离开的配置、不修改目标配置目录。

恢复官方登录不会删除当前目录的 `auth.json` 和 `config.toml`；只移除 API Key、切换官方 Provider，并保留令牌、会话记录和配置库。

所有生产写入必须经过 `atomic_write_bytes`、`write_text` 或 `atomic_copy_file`。原子写入在目标目录创建临时文件，刷新并 `fsync` 后通过 `os.replace` 替换。`save_codex_config` 和 `create_custom_template_config` 使用双文件快照回滚，新增写入路径不得绕过这些辅助函数。

配置库读取通过 `cached_profile_entry` 缓存签名和 Base URL。缓存键是规范化目录路径，失效依据是 `auth.json/config.toml` 的存在状态、大小、`mtime_ns` 和 `ctime_ns`；LRU 上限为 512。不要缓存 API Key 的展示文本，也不要取消基于文件状态的自动失效。

## 代码入口

- `CodexConfigApp`：主窗口、页面、弹窗和用户交互
- `classify_config_for_editing`：判断配置是否可编辑、需要模板或存在冲突
- `read_codex_config` / `save_codex_config`：读取和原位保存当前配置
- `fetch_available_models` / `parse_model_list`：请求并解析当前供应商的 OpenAI 兼容模型列表
- `save_active_model`：只修改当前 Model，并同步切换前匹配的配置库记录
- `create_custom_template_config`：创建稳定的自定义 Provider 模板
- `build_backup_signature` / `build_requested_signature`：生成配置核心签名
- `cached_profile_entry` / `clear_profile_cache`：配置签名和列表搜索缓存
- `atomic_write_bytes` / `atomic_copy_file`：同目录原子写入和复制
- `restart_codex_application`：识别、启动或重启 Codex，并按安装类型重新启动
- `find_matching_backup`：查找内容相同的配置库项目
- `create_named_backup` / `restore_backup`：创建和切换配置库项目
- `save_config_profile` / `update_config_profile`：保存新增配置和编辑配置
- `rename_backup` / `delete_backups`：重命名、单删和批量删除配置目录
- `apply_saved_profile`：以字段级合并方式应用 API 配置，保留当前会话、令牌和未知字段
- `restore_default_config`：切换官方登录时仅设置 `model_provider = "openai"` 并移除 API Key，不删除核心配置文件
- `acquire_single_instance` / `release_single_instance`：Windows 单实例互斥量
- `FlatVerticalScrollbar`：配置列表的扁平自绘滚动条

## 界面约定

- 主窗口固定为 `820 × 500`，无最大化按钮
- 自定义深色标题栏提供关于、最小化、关闭和窗口拖动
- 主窗口通过保留 `WS_CAPTION` 并拦截 `WM_NCCALCSIZE` 获得 Windows 任务栏动画；`_native_wndproc` 必须由实例持续持有，不能改成局部临时回调
- 主窗口任务栏只使用 `app_icon_title.png`；弹窗和 EXE 使用 `app_icon.ico`，不要用 `iconphoto(True, ...)` 覆盖全部弹窗
- 左侧功能顺序为当前配置、切换配置、官方登录、一键重启、新手引导
- 左侧“新手引导”下方提供“推荐渠道”入口，页面展示 AI Ark API 地址；点击地址使用系统默认浏览器打开
- 启动后后台查询 GitHub 最新 Release；网络失败必须静默，不影响主界面；“关于软件”提供手动检查入口
- 检测到新版本时只在关于图标右上角显示红点，不弹窗；关于窗口显示新版本并提供手动下载入口，不自动下载、不自动安装、不替换正在运行的 EXE
- Microsoft Store 版 Codex 必须在旧主进程完全退出并等待 Shell 清理托盘 GUID 后，通过 `explorer.exe` 的 AppsFolder AUMID 交由 Windows Shell 独立启动；不能使用会让 Codex 生命周期依附配置助手的直接 COM 激活
- 当前页面的 API Key、Provider 和 Base URL 只读；Model 可手动输入或通过供应商列表快速切换
- 点击“获取模型”才允许访问当前 Base URL；请求必须保持超时、大小限制和禁止重定向
- 当前页下拉选择 Model 后立即保存；手动输入在 Enter 或失去焦点时保存，Esc 放弃；若切换前匹配配置库记录，必须同步更新并在失败时回滚两边
- Model 下拉按钮使用内缩的小型线条 chevron；输入框和弹窗的左、右、上、下边线必须都保持 `2px`，其中按钮画布保留右侧内层边线，弹窗在隐藏滚动条后保留独立右侧内层边线；Clam 主题的 `Model.TCombobox` 与 `ComboboxPopdownFrame` 必须统一 `bordercolor`、`lightcolor`、`darkcolor`；弹出列表支持滚轮、方向键或键入定位
- README 使用 `docs/images/model-dropdown.png` 展示模型下拉选择，并使用 `docs/images/recommended-channel.png` 展示推荐渠道；更新对应界面时同步维护截图
- 配置列表双击整行均可切换，包括配置名称、Base URL 和行内空白区域
- 配置列表外围始终为浅灰细边框，选中只改变对应行背景
- 次要按钮使用统一浅灰背景，绿色按钮表示主要操作
- 瞬时消息使用无背景纯文字，位于右侧页面底部留白
- 眼睛按钮不显示悬停提示
- 多选右键菜单只能批量删除所选配置或退出多选，不能进入单项编辑
- 启动时询问是否打开新手引导；“是”进入导航页，“否”直接进入软件；仅在明确点击“不再弹出”后停止自动询问

## 单实例和退出

`main()` 在创建 Tk 窗口前获取 `Local\\z1099530893.CodexConfigTool` 互斥量。重复启动只显示提示，不读取或写入配置。关闭主窗口后 Tk 主循环退出，`finally` 释放互斥量；扫描线程使用 daemon，不阻止程序结束。

## 一键重启 Codex

`restart_codex_application()` 只识别 Codex 桌面应用，不应匹配普通 ChatGPT、命令行 Codex 或本工具自身。Windows Store 版本通过 `OpenAI.Codex` 包和窗口所属进程识别，普通安装版本通过可执行文件路径识别。Codex 未运行时，会通过 AppX 包或常见桌面安装路径寻找可启动目标并直接启动。

重启时先向 Codex 顶层窗口发送 `WM_CLOSE`，最多等待 8 秒，让 Codex 保存“跟随系统”等界面状态；即使没有枚举到顶层窗口，也会先完成等待，不会立即强制结束。只有进程仍未退出时才使用 `taskkill /F`。强制结束后必须重新枚举并确认同一 Codex 主程序已经完全消失，再等待 Windows Shell 清理固定托盘 GUID。随后按原安装类型启动：Store 版本使用 Explorer + AppsFolder AUMID，普通版本直接启动原可执行文件。正常关闭只能提供保存机会，不能保证 Codex 在超时强制结束前完成所有内存状态写入。修改该流程时不得退回默认强制结束，否则可能造成显示设置回退。

## 资源和打包

PyInstaller 必须从 `assets/` 包含：

```text
assets/donation_105.png
assets/donation_210.png
assets/app_icon.png
assets/app_icon_title.png
assets/app_icon_about.png
assets/title_about.png
assets/title_minimize.png
assets/title_close.png
assets/eye_smooth.png
assets/eye_off_smooth.png
assets/arkapi.png
assets/app_icon.ico
version_info.txt
```

使用 `scripts\build.bat` 或 `scripts\build.ps1` 构建原始单文件 EXE。安装 Inno Setup 6 后，使用 `scripts\build_installer.bat` 或 `scripts\build_installer.ps1` 同时生成版本化便携版与安装包。`dist/`、`build/`、`*.spec`、`__pycache__/` 已加入 `.gitignore`，不提交到源码仓库。两个发布产物均上传到 GitHub Releases。

安装包定义位于 `packaging/CodexConfigTool.iss`。安装范围固定为当前用户，默认目录为 `%LOCALAPPDATA%\Programs\CodexConfigTool`，不要求管理员权限；桌面快捷方式默认勾选但允许取消，并创建开始菜单与卸载入口。安装器只能打包应用 EXE，不得包含、迁移、删除或重置 `.codex`、`auth.json`、`config.toml`、会话目录或历史记录。

卸载器提供“保留用户数据 / 完全删除用户数据”两个单选项，默认保留。完全删除只清理 `%APPDATA%\CodexConfigTool` 和默认 `.codex\backups` 配置库，不扫描、不删除 `%APPDATA%\Codex`、`%LOCALAPPDATA%\Codex`，也不删除 `.codex` 根目录下除 `backups` 外的任何内容。第三方卸载工具可能误将 `%APPDATA%\Codex` 和 `%LOCALAPPDATA%\Codex` 识别为残留，必须提示用户不要删除这两个 Codex 本体目录。

## 验证清单

每次修改后执行：

1. `python -m py_compile codex_config_tool.py`
2. `python -m unittest discover -s tests -q`
3. 在临时 `APPDATA`、`CODEX_HOME` 下验证新增、编辑、切换、删除和官方登录
4. 验证取消保存不会修改任何配置文件
5. 验证原子替换失败时旧文件保持不变、临时文件被清理、双文件事务完整回滚
6. 验证缓存重复读取命中，并在文件替换后自动失效
7. 验证超过 5 个配置仍全部保留
8. 验证列表选择、拖选、全选、滚动条和弹窗按钮的 Windows 界面效果
9. 连续验证任务栏最小化/恢复动画，确认没有第二条系统标题栏
10. 验证 Codex 未启动时“一键重启”会改为启动 Codex，未找到安装时显示错误
11. 验证一键重启只处理 Codex 桌面应用，确认窗口取消时不执行任何操作
12. 验证正常关闭路径会保留 Codex 的“跟随系统”显示模式，并验证无窗口等待、超时回退、残留主进程阻止启动和 Store 版 Shell 独立启动路径
13. 实机确认重启后 Codex 主窗口、任务栏图标和系统托盘图标均恢复，托盘右键菜单可以退出 Codex
14. 关闭程序后确认进程结束，再进行 PyInstaller 打包，并检查 EXE 详细信息中的 `1.4.0` 版本
15. 构建安装包并验证桌面快捷方式默认勾选且可取消、开始菜单和卸载入口正常
16. 分别验证首次安装、同版本覆盖、升级覆盖和卸载，确认 Codex 配置、API Key 与聊天记录保持不变

## 后续修改原则

保持配置解析、Provider ID、官方登录流程和 Codex 桌面状态保护不变。涉及配置文件写入时，必须先在临时目录验证；完成后同步更新 README、HANDOFF、CHANGELOG 和版本号，并运行完整测试。

README 使用的产品截图统一保存在 `docs/images/`，使用稳定的英文文件名并直接提交到 Git。更新界面时应同步更新对应截图和说明，不得仅依赖聊天附件或外部图片地址。

已明确不做：引入正式 TOML 解析器、拆分主程序、外部并发检测、扫描路径重构、GUI 自动化测试和合并两套构建脚本。除非需求重新确认，不要把这些项目作为顺手重构加入。

## 会话保留约定

官方登录与 API 配置切换均为非破坏性字段合并。官方模式只移除 `OPENAI_API_KEY` 并切换到 `openai`；切回 API 时只更新 Provider、Base URL、Model 和 API Key。`config.toml`、`auth.json` 中的 ChatGPT 令牌与未知字段，以及 `sessions/`、`archived_sessions/`、`history.jsonl` 等会话数据必须保留。两份核心文件的写入失败时必须整体回滚。

## Developer test helper

`scripts\reset_onboarding.bat` is provided for repeatable onboarding testing. Run it after choosing "Do not show again" in the application. It updates `%APPDATA%\CodexConfigTool\settings.json` by removing only `hide_onboarding`; it must not delete or replace the entire settings file, and it does not modify the Codex configuration directory or official login files. Restart the application after the script completes to show the onboarding prompt again.
