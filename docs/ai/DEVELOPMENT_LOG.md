# 开发记录

## DEV-027 - 2026-08-31 - 统一保存与双击应用配置事务

阶段和模式：Iterative Development / Development + Packaging validation
相关 ID：CR-006、BUG-004、P-004E、P-006I、P-006J、TEST-006
客户反馈与确认：客户实测前 9 项通过；第 10 项发现双击当前配置在 Codex 未运行时无法启动，并确认“保存并使用/保存并应用”与双击自动生命周期冲突。最终确认当前配置页模型只读，新增/编辑仅单一保存，双击配置是唯一应用、启动和自动重启入口。
基线：已有自动退出、同步、投影和启动事务，但双击当前配置直接返回；活动配置编辑可以被旧 live `config.toml` 在切换前反向覆盖；当前页、新增页和编辑页存在不一致的模型写入时机。
工作内容：新增受 `.codex\backups` 边界校验的待应用活动配置路径；编辑活动配置只保存配置库并标记待应用；切换事务在待应用时跳过旧 live 同步，成功后清除标记，失败恢复 live、配置库、活动与待应用设置。双击当前配置在 Codex 停止时进入启动事务；运行且无待应用修改时提示已运行；存在待应用修改时确认后正常退出、应用并重启。当前配置页启动默认模型改为只读并移除获取/下拉/编辑；新增和编辑移除“保存并使用/保存并应用”，完整模型列表只在单一保存事务中落盘。
安全边界：待应用设置只保存配置库路径，不包含 API Key；未读取或修改真实 `.codex`、Codex 私有会话数据库、聊天记录或未知 `%SystemDrive%/` 目录。
回滚点：`build/rollback/dev027-unified-profile-activation/`，包含修改前主程序、测试和项目状态/计划，不包含真实 Codex 数据或敏感信息。
验证证据：`python -m py_compile codex_config_tool.py tests\test_backup_management.py` 通过；117 项标准库测试通过；`git diff --check` 无空白错误；PyInstaller 6.20.0 单文件构建成功；隔离 APPDATA、LOCALAPPDATA、USERPROFILE 和 HOME 启动 4 秒保持运行，随后精确关闭测试实例，未触碰真实 Codex 目录。
预览产物：`dist/final/CodexConfigTool-Preview-UnifiedActivation.exe`，大小 13,139,523 字节，SHA-256 `31C32FDD4AAF8E8DF10FB2423BBBC9C8BC2DA9F196F1F581143E0579C8D1542E`。
结果：FIXED-BUT-CLIENT-RETEST；等待客户按新流程验证双击当前配置启动、活动配置待应用、A→B→A、聊天保留以及主窗口/任务栏/系统托盘。
待处理 Git 操作：未获得新的提交、推送、Tag 或 Release 授权，保持未提交状态。

## DEV-026 - 2026-08-31 - 配置切换整合自动正常退出与启动事务

阶段和模式：Iterative Development / Development + Packaging validation
相关 ID：CR-006、BUG-004、P-004E、P-006I、TEST-004、TEST-006
客户确认：独立重启连续三次实测主窗口、任务栏、系统托盘和托盘右键退出均正常；恢复配置切换自动重启，但移除左侧独立“一键重启”。切换须保存原配置公开模型和推理强度，再应用目标配置并启动。
基线缺陷：运行中首次拒绝后再次操作可能进入切换；失败后重开配置助手可能显示“未保存配置”；公开推理强度变化与旧测试预期冲突；手动生命周期与“切换时保存公开默认值”目标不一致。
工作内容：`switch_saved_profile` 改为“确认权限→正常退出→同步身份一致的原配置→投影目标→更新活动标记→Windows 正式入口启动”；退出前零写入，切换期间 UI 不可重入；投影失败恢复当前三份受管文件、原配置库文件和设置标记并尝试启动原 Codex；目标启动失败且没有残留新进程时同样回滚；检测到部分启动进程时不在运行中反向覆盖配置。移除左侧独立重启入口，更新配置列表、新手引导和文档。
安全边界：不使用 taskkill、不强制结束、不读取或修改 Codex 私有会话数据库；不删除聊天记录；未操作真实 `.codex`、API Key 或未知 `%SystemDrive%/` 目录。
回滚点：`build/rollback/dev026-profile-switch/` 保存修改前主程序和测试副本；构建目录被 Git 忽略，不进入发布包。
验证证据：Python 语法检查、109 项标准库测试、`git diff --check`、PyInstaller 单文件构建和隔离四个用户目录启动 3 秒通过。
预览产物：`dist/final/CodexConfigTool-Preview-AutoSwitch.exe`，大小 13,142,351 字节，SHA-256 `F0B187C4BEF2439D918FF3EA2FF8160D5213E633761198089ABD22B1A5F70854`。
结果：FIXED-BUT-CLIENT-RETEST；等待客户实测 A→B→A 自动生命周期、公开默认值同步、聊天保留和托盘状态。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-025 - 2026-08-31 - Ctrl+Q 注入时序与重启按钮恢复修复

阶段和模式：Iterative Development / Development + Acceptance diagnosis
相关 ID：BUG-004、P-004E、TEST-004
客户复测：点击“一键重启”后 Codex 窗口会切到前台，但不会退出；等待 20 秒仍无错误提示且按钮持续禁用。手动在 Codex 中按 `Ctrl+Q` 可以正常退出。
根因结论：Codex 的退出快捷键有效，问题位于配置助手。首轮修复后客户得到明确退出失败提示，确认窗口已激活但按键仍未注入。底层检查发现原 Win32 `INPUT` 联合体只声明键盘成员，在 64 位 Windows 中错误生成 32 字节结构，而 `SendInput` 要求包含鼠标、键盘和硬件成员的 40 字节原生 ABI，因此系统拒绝输入。异常回调还延迟引用了 Python 离开 `except` 后会被清除的 `exc`，导致旧版按钮和错误提示无法恢复。
工作内容：补全 Win32 `INPUT` 的鼠标、键盘和硬件联合体并验证 64 位结构为 40 字节；等待已核验的 Codex 窗口稳定处于前台后，按真实按键节奏分别发送 Ctrl 按下、Q 按下、Q 抬起、Ctrl 抬起；失败路径确保释放 Ctrl；重启后台线程捕获常规异常并在调度 Tk 回调前固化错误文本，保证所有失败均恢复按钮并显示原因。
安全边界：未使用 taskkill 或强制结束；旧 Codex 未完全退出时不启动第二实例；未修改真实 `.codex`、API Key、配置或聊天记录。
验证证据：Python 语法检查、106 项标准库测试（含本机 64 位 Win32 `INPUT` ABI 尺寸检查）、`git diff --check` 和 PyInstaller 单文件构建通过。
预览产物：`dist/final/CodexConfigTool-Preview-SafeRestart.exe`，大小 13,142,290 字节，SHA-256 `4EB637A732AA207D28C353D0DCC10AD07CF911C611E707FA9FB8FC930A5221B5`。
结果：FIXED-BUT-CLIENT-RETEST；等待客户验证自动退出、重新启动、任务栏、系统托盘和托盘右键退出。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-024 - 2026-08-31 - 使用 Codex 自身 Ctrl+Q 正常退出

阶段和模式：Iterative Development / Development + Acceptance diagnosis
相关 ID：BUG-004、P-004E、TEST-004
客户复测：固定托盘 GUID 清理预览点击“一键重启”后，Codex 没有退出，因而没有进入后续重新启动流程。
根因证据：当前 Codex 进程树保持完整；已安装 Electron 主进程源码显示 `before-quit` 可阻止一般退出，同时 Windows 应用菜单明确追加 `Ctrl+Q`，其菜单项使用 Electron `role: quit`，与托盘“退出”的 `app.quit()` 汇入同一退出生命周期。因此 Cockpit Tools 的不带 `/F` taskkill 在当前 Codex 版本上并不可靠。
工作内容：删除 taskkill 关闭路径；枚举并恢复属于 Codex 的顶层窗口，调用 `SetForegroundWindow` 后再次核验前台窗口 PID，确认无误才使用 `SendInput` 发送完整 Ctrl 按下、Q 按下、Q 抬起、Ctrl 抬起序列；等待所有桌面宿主退出后再清理固定托盘 GUID并从 AppsFolder 启动。任何窗口、焦点、输入或退出失败均停止，不强杀、不启动第二实例。
安全边界：快捷键发送前必须核验前台 PID 属于本次识别的 Codex 进程；未修改真实 `.codex`、API Key、配置或聊天记录；未在当前承载对话的 Codex 上执行快捷键。
验证证据：Python 语法检查、104 项标准库测试、`git diff --check` 和 PyInstaller 构建通过。
预览产物：`dist/final/CodexConfigTool-Preview-SafeRestart.exe`，大小 13,140,925 字节，SHA-256 `360D9F7518FBCE64B13C3373D78B5B457835D34910C8EE8F787CD11D546A718A`。
结果：FIXED-BUT-CLIENT-RETEST；等待客户验证 Codex 自动退出、重新启动、系统托盘图标和右键退出。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-023 - 2026-08-30 - Store 固定托盘 GUID 残留清理

阶段和模式：Iterative Development / Development + Acceptance diagnosis
相关 ID：BUG-004、P-004E、TEST-004
客户复测：正常打开 Codex 后使用上一预览“一键重启”，主窗口恢复但系统托盘图标仍未出现。
现场证据：Windows 应用枚举确认新实例包身份为 `OpenAI.Codex_2p2nqsd0c76g0!App`；进程树确认根进程父进程为 `explorer.exe`；新主进程和主窗口均存在。因此排除 AUMID、Shell 启动入口和父子生命周期错误。
源码证据：只读提取本机已安装 Codex 26.825.5331.0 的 Electron 主进程代码；Windows Store 正式版使用固定托盘 GUID `e5768d8b-6936-4f45-b1ad-4c5fb414cb35` 创建 `Tray` 并等待 `whenReady()`，托盘退出调用 `app.quit()`。taskkill 后该 GUID 的 Explorer 注册可能残留，新窗口仍可显示但托盘初始化失败。
工作内容：新增 Store 正式包与固定 GUID 的精确映射；旧主进程完全退出后调用 `Shell_NotifyIconW(NIM_DELETE)` 清理该 GUID，再等待原有 Shell 收敛时间并走 AppsFolder 正式入口；普通 EXE、其他包身份和其他软件托盘图标不处理。
数据边界：未修改真实 `.codex`、API Key、配置或聊天记录；现场仅做窗口、进程树和已安装程序源码的只读诊断；未重启当前 Codex。
验证证据：Python 语法检查、103 项标准库测试、`git diff --check` 和 PyInstaller 构建通过；低层模拟确认 `Shell_NotifyIconW` 收到 `NIM_DELETE`、`NIF_GUID` 和准确 UUID 字段。
预览产物：`dist/final/CodexConfigTool-Preview-SafeRestart.exe`，大小 13,140,172 字节，SHA-256 `4D02F0C4A44AE75DA208D1D8B202364F766B8672F5AACA856484C47D1CECEB1E`。
结果：FIXED-BUT-CLIENT-RETEST；等待客户再次验证系统托盘图标和右键退出。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-022 - 2026-08-30 - Windows 原生入口自动启动与重启

阶段和模式：Iterative Development / Development
相关 ID：BUG-004、P-004E、TEST-004
客户目标：配置助手自动启动或重启 Codex，结果必须与桌面快捷方式或开始菜单启动一致，主窗口、任务栏、系统托盘和托盘右键退出均可用；不接受要求用户先手动退出的半自动方案。
参考研究：核对 `jlcodes99/cockpit-tools` 公开源码；其 Windows 实现优先读取 Codex AppX 的真实 AUMID、走系统应用入口、等待新主进程，关闭时先使用不带 `/F` 的 `taskkill`，系统入口失败后才回退 EXE，且 EXE 不使用 `CREATE_NO_WINDOW`。
工作内容：新增 AppX 清单与 `Get-StartApps` AUMID 发现；自动请求 Codex 正常退出并等待完全结束；退出失败不强杀、不启动第二实例；AppsFolder 启动后确认新主进程和主窗口；已知真实 EXE 时提供受控回退；UI 恢复全自动确认与进度提示。配置切换仍保持运行中拒绝、手动生命周期，不调用本入口。
数据边界：未读取、修改或输出 API Key；未修改真实 `.codex`、聊天记录、会话数据或未知 `%SystemDrive%/` 目录；只读发现本机 AUMID。
验证证据：`python -m py_compile codex_config_tool.py` 通过；101 项标准库测试通过，覆盖清单 AUMID、开始菜单发现脚本、非强制退出、退出失败零启动、新主进程确认、包入口启动和 EXE 回退启动标志。
预览产物：`dist/final/CodexConfigTool-Preview-SafeRestart.exe`，大小 13,038,742 字节，SHA-256 `3A857B333E2BDD9A4AB522EB683D7F6141609FF68647BBA5D3AB6B38BD4C5118`。
结果：FIXED-BUT-CLIENT-RETEST；构建已完成，等待客户真实系统托盘验收。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-021 - 2026-08-30 - 独立重启入口改为安全半自动流程

阶段和模式：Iterative Development / Development
相关 ID：BUG-004、P-004D、TEST-004
客户反馈：配置切换已取消自动重启，但独立“一键重启”入口仍会偶发造成 Codex 系统托盘图标缺失；客户要求先定位原因，再按 Codex 自身托盘退出和正常启动方式修改。
诊断结论：旧流程发送 `WM_CLOSE`，超时后调用 `taskkill /T /F`，固定等待后只验证主窗口恢复，不验证托盘控制器；这不等价于 Codex 托盘菜单的正常退出。当前 Store 启动已由 Windows Explorer 执行，主要风险位于关闭生命周期。
工作内容：保留现有“一键重启”导航入口；运行中提示用户从系统托盘正常退出，后台只读等待同一 Codex 桌面应用最多 120 秒，确认完全退出后按安装类型启动；删除窗口关闭、进程树强杀及相关辅助函数；等待超时只报错，不启动、不结束进程。
验证证据：Python 语法检查通过；定向测试通过；97 项完整标准库测试通过；覆盖 Codex 未运行时直接启动、运行中等待正常退出后启动、确认前退出竞态、超时不启动且不调用进程命令、配置切换不调用重启入口；PyInstaller 单文件构建成功，隔离四个用户目录启动 3 秒仍存活。
回滚：修改前文件级副本记录于 `BACKUP_MANIFEST.md`，未触碰真实 `.codex`、API Key、聊天记录或未知 `%SystemDrive%/` 目录。
预览产物：`dist/final/CodexConfigTool-Preview-SafeRestart.exe`，大小 13,036,417 字节，SHA-256 `DB10E17C232108625706CE032A710F6CB7146D78EDAADB61230B9875F89585EB`。
结果：FIXED-BUT-CLIENT-RETEST；源码、自动测试、构建和隔离启动完成，待客户验证主窗口、任务栏、系统托盘及右键退出菜单。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-020 - 2026-08-30 - 配置切换改用 Codex 自身退出与启动

阶段和模式：Iterative Development / Development
相关 ID：CR-006、BUG-004、P-006H、TEST-006
客户反馈：双击切换触发的配置助手重启仍会偶发导致 Codex 系统托盘图标缺失，无法右键退出；客户要求移除配置切换自动重启，改用 Codex 托盘右键退出和桌面、开始菜单或任务栏手动启动。
风险判断：Codex 运行时直接投影目标配置不安全，旧进程退出持久化可能覆盖目标 API Key；配置助手也无法等价调用 Codex 自身托盘菜单。因此采用“运行中拒绝且零写入，用户正常退出后再切换”的流程。
工作内容：新增 `is_codex_application_running` 只读检测；`switch_saved_profile` 移除关闭、强制结束、失败补启和成功启动调用；运行中在同步前抛出明确提示；已退出时只同步公开启动默认值、投影目标配置和更新活动标记；配置列表页、新手引导和完成提示改为手动生命周期说明。
兼容边界：独立“一键重启”按钮暂时保留为可选功能，但配置切换不再调用它；BUG-004 从 ACCEPTED 撤回为 RETEST，不能声称独立重启托盘问题已修复。
验证证据：Python 语法检查通过；2 项定向测试和 97 项完整标准库测试通过；运行中路径验证当前配置与活动配置均不变化，且同步、投影、关闭、启动函数均不被调用；`git diff --check` 通过；PyInstaller 单文件构建成功；隔离四个用户目录启动 3 秒仍存活。
预览产物：`dist/final/CodexConfigTool-Preview-ManualSwitch.exe`，大小 13,037,752 字节，SHA-256 `76C7B353D2CB37F3834CB3626321CD03888685F569316665C4C7C83F899B27BB`。
结果：FIXED-BUT-CLIENT-RETEST；需要客户完成“托盘右键退出→双击切换→手动启动”，确认目标配置、对话能力和系统托盘图标。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-019 - 2026-08-30 - 启动默认值语义修正与预览包

阶段和模式：Iterative Development / Development
相关 ID：CR-006、P-006G、TEST-006
客户实测：A 的对话内模型从 `deepseek-v4-flash` 临时切到 Pro、B 的对话内推理强度从中临时切到高后，A→B→A 仍分别恢复配置库原先的 Flash 与 Sol-中；双击切换每次都会自动重启 Codex。
结论：Codex 对话内选择没有写回公开 `.codex/config.toml`；配置助手只能同步公开配置和自有模型目录。此前“切换前会承接对话内选择”的产品描述不成立，但目标配置投影和自动重启流程本身正常。
客户确认：每个配置保存启动默认模型和默认推理强度；对话内临时选择只影响对应对话，不自动覆盖配置库；不读取或修改 Codex 私有应用数据库；双击切换继续自动关闭、投影并重启 Codex。
工作内容：`sync_current_to_active_profile` 和 `apply_saved_profile` 注释改为公开启动默认值边界；当前配置及新增/编辑界面的 Model 标签统一为“启动默认模型”；当前页保存提示和新手引导同步修正；测试名称、README、交接、变更、计划、验收和状态记录不再承诺私有线程状态回写。
数据边界：未读取或修改真实 `.codex`、API Key、聊天记录或 Codex 私有数据库；保留现有候选配置目录发现和 `models_cache.json` 只读兼容逻辑。
验证证据：Python 语法检查通过；96 项标准库测试通过；`git diff --check` 通过；PyInstaller 单文件构建成功；隔离 `APPDATA`、`LOCALAPPDATA`、`USERPROFILE`、`CODEX_HOME` 启动 3 秒仍存活。
预览产物：`dist/final/CodexConfigTool-Preview-LaunchDefaults.exe`，大小 13,038,377 字节，SHA-256 `671E6A636E241FC6D4F3976EF726AEBF20CB9F25424992F668C535306804E68B`。
结果：FIXED-BUT-CLIENT-RETEST；需要客户验证 A→B→A 启动默认值恢复、对话内临时选择不覆盖配置库，以及自动重启后的窗口、任务栏和系统托盘图标。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-018 - 2026-08-29 - Codex 原生模型元数据优先

阶段和模式：Iterative Development / Development
相关 ID：CR-006、P-006G、TEST-006
客户确认：OpenAI 模型的显示名称、推理强度和能力元数据应采用 Codex 自身定义；只有第三方未知模型才由配置助手生成兼容元数据，且不得改变 Provider 路由。
基线与回滚：在仓库外创建 `CodexConfigTool-native-metadata-2026-08-29T02-36-44-300Z` 文件级副本；未包含真实 `.codex`、API Key、聊天记录或构建产物。
工作内容：新增对当前 Codex 根目录 `models_cache.json` 的只读容错解析；自定义 Provider 的模型 slug 仅在完全且区分大小写匹配时整条深拷贝原生条目，不根据 `gpt` 前缀猜测；原生与第三方条目可在同一目录共存；缓存缺失、损坏或无匹配时继续生成第三方兼容条目，不阻断保存。配置库写入显式复用当前根目录缓存，不把缓存复制进配置库。
官方 Provider：`model_provider = "openai"` 时不创建配置助手自有目录；历史 owned 引用只从当前投影中清除，配置库源文件不改；用户 external 目录不读取、不覆盖、不删除。
路由边界：未改写 Provider、Base URL、API Key 或真实模型 slug；模型元数据只影响 Codex 的模型展示和能力菜单，不承担请求路由。
验证证据：Python 语法检查通过；96 项标准库测试通过，覆盖原生整条复用、前缀/大小写非匹配、混合目录、根缓存供配置库复用、官方 Provider、external 保护、缓存异常降级和旧目录只迁移当前投影；`git diff --check` 通过；PyInstaller 单文件构建成功；隔离四个用户目录启动 3 秒仍存活。
预览产物：`dist/final/CodexConfigTool-Preview-NativeMetadata.exe`，大小 13,038,063 字节，SHA-256 `E547D1091329FBFFCD47F0A1BA5D312E6F772D68004D38EE949DC895040EAABC`。
结果：FIXED-BUT-CLIENT-RETEST；需要客户在真实 Codex 中验证自定义 Provider 混合模型菜单及切换回官方 OpenAI Provider 的表现。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-017 - 2026-08-29 - 运行中配置切换凭据覆盖与推理强度修复

阶段和模式：Iterative Development / Development + Acceptance diagnosis
相关 ID：CR-006、P-006E、P-006F、TEST-006
客户实机反馈：从可用 `deepseek-v4-flash` 配置切换到原本使用 GPT 5.6 Sol 的配置后，对话持续重连，推理强度菜单只剩“中”；客户澄清 Sol 与 Terra 截图来自不同会话，不属于显示名错配。
只读诊断：当前 `config.toml` 已指向目标配置的 Provider、Base URL 和模型，但当前 `auth.json` 的 API Key 与目标配置不一致，且与另一个已保存配置一致；未输出、记录或写入任何 API Key。旧模型目录把当前 `model_reasoning_effort` 写成仅有的支持能力，因此 Codex 菜单只显示一个强度。
根因：原切换流程在 Codex 仍运行时先投影目标文件，并提示用户随后手动重启；旧 Codex 接收关闭事件时会持久化内存状态，可能把旧凭据重新写回已经切换的 `auth.json`，形成“目标 Provider + 其他配置 Key”。
工作内容：拆分关闭和启动生命周期；配置切换改为后台执行“关闭 Codex并等待退出→回写身份一致的当前配置→投影目标配置→更新活动标记→重新启动”；模型目录改为低/中/高/超高四档，当前值只决定默认档；应用配置助手自有旧目录时只升级当前投影的推理元数据，不修改配置库原文件。
数据边界：只对真实配置进行非敏感字段和匿名一致性检查；未修改真实 `.codex`、聊天记录、会话数据或 API Key；未将匿名指纹写入项目文档。
验证证据：Python 语法检查通过；87 项标准库测试通过，新增关闭/回写/恢复/启动顺序、目标凭据在启动前正确、标准推理菜单和旧目录无损升级覆盖；`git diff --check` 通过；PyInstaller 单文件构建成功；隔离 APPDATA 启动 3 秒仍存活。
预览产物：`dist/final/CodexConfigTool-Preview-SwitchFix.exe`，大小 13,018,374 字节，SHA-256 `E565AFEE1229757B8CA4DF534BD6F789554AC63254BBA81FD37D9C32ECD93185`。
结果：FIXED-BUT-CLIENT-RETEST；等待真实 Codex 验证 A→B 自动重启、B 对话连接和四档推理强度菜单。
待处理 Git 操作：未获得新的提交、推送或 Release 授权，保持未提交状态。

## DEV-016 - 2026-08-28 - 每配置完整模型目录与切换状态修复

阶段和模式：Iterative Development / Development
相关 ID：CR-006、P-006A、P-006B、P-006C、P-006D、TEST-006
客户确认：获取的模型列表必须按配置保存；当前、新建、编辑页面统一；Codex 内选择模型后在切换前回写；切换后恢复目标配置的默认模型、推理强度和完整模型目录；不影响聊天记录。
根因审查：`save_active_model` 在选模后删除自有目录；当前页双目标保存不原子；新建/编辑先保存或应用、再二次写目录；新建错误继承当前目录；切换仅重建当前模型单条目录并遗漏 `model_reasoning_effort`；活动配置路径未验证 Provider 身份。
工作内容：新增完整目录解析校验、手动模型追加、双目标原子保存和身份一致性解析；选择模型保留完整目录；模型列表进入创建/编辑核心事务；新建默认不继承目录；切换完整投影 owned/none/external 状态与推理强度；外部目录只保留引用且不接管文件；磁盘写入错误和配置冲突均恢复 auth/config/自有目录三文件快照。
数据边界：未读取、输出或记录 API Key；未修改真实 `.codex`；未删除或更改 `sessions`、`archived_sessions`、`history.jsonl` 等聊天数据。
验证证据：语法检查通过；84 项标准库测试通过，覆盖目录保留、A/B 隔离、推理强度、无目录、外部目录、磁盘错误/配置冲突回滚、损坏目录拒绝切换、身份误写保护和 API→官方→API 会话保留；`git diff --check` 无空白错误；PyInstaller 最终源码构建成功；隔离启动冒烟通过。
预览产物：`dist/final/CodexConfigTool-Preview-ModelAlias.exe`，大小 13,017,520 字节，SHA-256 `767F23DC3361664B90FCB3EECC64B4A8EB2182256C7FE919A5979E813E7C02FE`。
结果：实现与本地验证 GO，等待客户真实 Codex 环境复测。
待处理 Git 操作：本轮没有提交、推送或 Release 授权，保持未提交状态。

## DEV-012 - 2026-08-28 - 模型显示别名预览便携包

阶段和模式：Development
相关 ID：CR-006、P-006A、P-006B、P-006C、P-006D、TEST-006
客户请求：借鉴 CC Switch，先提供模型显示别名与真实路由分离的预览便携包测试。
工作内容：新增配置助手自有 `codex-config-tool-model-catalog.json`；真实模型 ID 始终写入顶层 `model` 与目录 `slug`，显示别名写入 `display_name`；模型变更清除旧别名；配置切换、官方模式和失败回滚同步三份受管文件；用户自有 `model_catalog_json` 不被覆盖；当前配置页增加可编辑“模型显示名称”，保留手动输入模型和获取模型列表。
明确排除：未实现 Chat Completions/Anthropic 协议转换、本地常驻代理或多供应商自动路由。
验证证据：Python 语法检查通过；73 项标准库测试通过；隔离 Tk 启动尺寸检查通过（窗口 820×500，控件均在边界内）；PyInstaller 单文件构建成功；预览 EXE 启动冒烟通过。
预览产物：`dist/CodexConfigTool-Preview-ModelAlias.exe`，SHA-256 `6CC151379CBCD267B01B9E9BCC1CB431FE2AB6DA25E827AD2FCA3B5CE4336C63`。
结果：技术验证 GO，等待客户在真实 Codex 环境确认模型目录是否被读取、模型菜单是否显示别名以及请求路由仍使用真实模型 ID。
待处理 Git 操作：无授权，不提交、不推送、不创建 Release。
下一步：客户下载预览包，使用隔离或现有配置完成真实 Codex 复测。

## DEV-015 - 2026-08-28 - 自动模型列表与后台显示名称

阶段和模式：Development
相关 ID：CR-006、P-006B、P-006C、TEST-006
客户确认：移除用户手动填写模型显示名，获取模型列表后自动保存并生成显示名称。
工作内容：新增供应商模型列表目录生成；模型条目自动生成 `display_name`，真实 `slug` 保持不变；当前配置页和新建/编辑配置均提供获取模型入口；获取结果同步写入当前配置及活动配置库；保留手动输入模型兜底。
验证证据：Python 语法检查通过；68 项标准库测试通过；PyInstaller 预览便携包构建成功。
结果：自动模型目录预览版完成，等待客户复测。

## DEV-014 - 2026-08-28 - 配置切换前自动回写当前配置

阶段和模式：Development
相关 ID：CR-006、P-006C、TEST-006
客户确认：用户在 Codex 内切换模型后，下次切换配置时自动把当前配置复制并覆盖回原配置库。
工作内容：新增配置助手自己的当前配置路径标记；切换配置前自动回写当前 `auth.json`、`config.toml` 及自有模型目录；应用目标配置后更新标记；外部模型目录不覆盖；不复制会话、历史记录或其他聊天数据。
验证证据：Python 语法检查通过；68 项标准库测试通过；预览便携包重新构建成功。
结果：配置切换具备写回缓存行为，等待客户复测 Codex 内改模型后切换配置的场景。

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
# DEV-028 - 2026-08-31 - OpenAI 原生模型目录隔离

阶段和模式：Development + Packaging validation
相关 ID：CR-006、P-006J、TEST-006
客户反馈：A→B 配置复测中，OpenAI 原生模型的模型版本、推理强度和最高档位被配置助手模型列表影响；要求原生 OpenAI 配置保持 Codex 原生能力，第三方模型继续支持自动获取列表。
根因：保存模型列表和创建配置副本的通用路径仍可能把 `available_models` 传入 OpenAI Provider，触发配置助手目录处理或后续元数据投影。
工作内容：新增统一 `is_codex_native_provider` 判定；OpenAI 原生配置在模型目录保存入口直接清理/跳过助手目录；创建配置副本时忽略原生 Provider 的 `available_models`，继续保留其公开 `model` 和 `model_reasoning_effort`。
数据边界：未修改真实 `.codex`、API Key、聊天记录或 Codex 私有数据库；第三方 Provider 的模型目录逻辑保持不变。
验证证据：Python 语法检查通过；118 项标准库测试通过，新增 OpenAI 原生配置忽略模型列表且保留模型/推理强度回归测试；`git diff --check` 通过。
结果：实现完成，待客户复测 OpenAI 原生配置与第三方配置往返切换及最高推理档位。
待处理 Git 操作：未获得提交、推送或 Release 授权，保持未提交状态。
## DEV-029 - 2026-08-31 - 新增与编辑弹窗高度修正

阶段和模式：Development + UI validation
相关 ID：CR-006、P-006J、TEST-006
客户反馈：新增和编辑配置弹窗底部存在大块空白，窗口高度接近并超出主界面视觉边界。
根因：共用弹窗固定为 `570×450`，内容最底部仅到约 `396px`，多余高度形成明显空白。
工作内容：将新增和编辑共用弹窗统一调整为 `570×410`，不改变字段、按钮和模型下拉的尺寸或间距；增加尺寸回归断言。
验证证据：Python 语法检查通过；118 项标准库测试通过；隔离 Tk 实际布局测量显示新增、编辑窗口均为 `570×410`，最底部按钮结束于 `396px`，保留 `14px` 底边距；`git diff --check` 通过。
结果：FIXED-BUT-CLIENT-RETEST；等待客户确认实际 DPI 和字体环境下弹窗视觉效果。
待处理 Git 操作：未获得提交、推送或 Release 授权，保持未提交状态。
## DEV-030 - 2026-08-31 - JM2 推荐渠道与弹窗提示行合并

阶段和模式：Development + UI validation
相关 ID：CR-007、P-006J、TEST-006
客户反馈：推荐渠道需要新增 `jm2api.lol`；前次缩短弹窗后，模型行与操作按钮之间仍有一整行空白。
根因：空白来自固定占位的错误/模型获取状态标签，并非底部边距；直接继续裁剪高度会使动态提示或按钮越界。
工作内容：将提示标签移入按钮行左侧，按钮行上移并把新增/编辑弹窗调整为 `570×385`；推荐页抽取统一渠道行渲染，保留 AI Ark API 并新增 JM2 API。已将站点图标作为本地资源 `assets/jm2api.png` 打包，推荐页不依赖运行时远程 favicon。
验证证据：Python 语法检查、118 项标准库测试和 `git diff --check` 通过；隔离 Tk 测量确认提示出现时仍位于按钮行内，按钮最底部 `369px`；JM2 图标约 `38×40px`，名称和网址均在主窗口边界内。
结果：FIXED-BUT-CLIENT-RETEST；等待客户确认实际显示和链接打开行为。
待处理 Git 操作：未获得提交、推送或 Release 授权，保持未提交状态。

## DEV-031 - 2026-09-01 - v1.4.0 源码与发布候选整理

阶段和模式：Release preparation
相关 ID：CR-008、P-007A、P-007B、P-007C、TEST-007
客户请求：整理当前源码和文档，使用新版正式界面截图更新项目说明，提交 GitHub，并按现有版式重建 `v1.4.0` 标签、发布包和发布页。
基线：`main`、`origin/main` 和旧 `v1.4.0` 均位于 `12b5086c11d40d1a7b70b0ffddedab59e6c834ec`；本地保留前几轮完整功能、测试和文档改动；旧 Release ID 为 `377653760`。
工作内容：更新当前配置、配置列表、官方登录、新手引导、推荐渠道、关于和赞赏 7 张截图；替换 JM2 正式网站图标；清理 README、CHANGELOG 和发布说明中的过时行为；补齐构建脚本资源校验；忽略并保留误展开的 `%SystemDrive%/` 本地目录，不发布其中内容。
验证证据：Python 3.12.13 语法检查、118 项标准库测试和 `git diff --check` 通过；PyInstaller 6.20.0 干净构建与 Inno Setup 6.7.3 编译通过；便携版文件版本为 `1.4.0`，隔离启动 4 秒保持运行，实际解包目录包含 `assets/jm2api.png`；两个正式资产 SHA-256 已写入发布说明。
结果：发布候选为 GO；`main`、`v1.4.0` 标签、Release 说明、两个资产和 GitHub 源码归档统一以本提交为发布源。
待处理 Git 操作：无；`v1.0.0` 至 `v1.3.0` 保持不变。
下一步：客户复测真实 Codex 配置切换、任务栏和系统托盘流程。

## DEV-032 - 2026-09-01 - 补换新增与编辑配置脱敏截图

阶段和模式：Release correction
相关 ID：CR-008、P-007A、TEST-007
客户反馈：README 的新增与编辑配置截图未随其他界面更新；首次补发截图包含可识别 Base URL，随即提供了重新模糊连接信息的版本。
工作内容：只将第二张脱敏附件写入 `docs/images/model-dropdown.png`；第一张包含明文连接地址的附件未写入仓库、未提交、未推送或上传 Release。同步将发布记录中的正式截图数量修正为 8 张。
验证证据：图片为 `820×500` PNG，最终 SHA-256 `999A4BD0BC2BB6BCC42779657684BF670ACF06B22AAD28AEAAEABDEC93599F65`；README 继续使用稳定相对路径 `docs/images/model-dropdown.png`。
结果：截图修正完成，不影响已验证源码和两个 EXE 的内容及 SHA-256。
待处理 Git 操作：将本次文档修正快进推送到 `main` 并再次移动 `v1.4.0` 到修正提交，然后继续重建现有 Release。

## DEV-033 - 2026-09-01 - 新增与编辑配置补充 OpenAI 原生模型提示

阶段和模式：Release correction + packaging validation
相关 ID：CR-006、CR-008、P-007B、TEST-007
客户请求：在新增与编辑配置的文字说明中明确 Codex 使用 OpenAI 原生模型时不需要获取模型列表。
工作内容：弹窗单行副标题和新手引导明确“OpenAI 原生模型无需获取列表，获取模型仅用于第三方 Provider”；README 和发布说明补充原生模型、显示名称和推理强度由 Codex 管理的边界；同步更新脱敏截图中的副标题。
验证证据：Python 语法检查、118 项标准库测试和 `git diff --check` 通过；PyInstaller 6.20.0 与 Inno Setup 6.7.3 重建通过；隔离启动 4 秒保持运行并确认 JM2 资源存在。
结果：程序、说明、截图和两个正式产物已同步；新哈希写入发布说明、验收报告和发布报告。
待处理 Git 操作：快进推送本次修正并移动 `v1.4.0` 到最终提交，然后替换现有 Release 的两个资产和说明。
