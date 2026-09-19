# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配置：Qt（PySide6）前端。

与 ``CodexConfigTool.spec`` 的区别，每一条都有原因：

* 入口是 ``codex_config_qt.py``，输出名带 ``-Qt`` 后缀。**绝不覆盖**
  ``dist/CodexConfigTool.exe``——那是 Tk 版的回滚产物，也是当前发布链
  （``scripts/build.ps1`` → ``build_installer.ps1``）的输入。在 Qt 版被人工确认
  之前，两个产物必须并存。
* ``upx=False``。UPX 压缩 ``Qt6*.dll`` 是已知的崩溃来源，而体积收益集中在 Qt
  运行时上，风险与收益不成比例。（Tk 版没有这个问题，所以那边保持 ``upx=True``。）
* 需要收集 PySide6 运行时，因此显式排除用不到的 Qt 模块。前端只导入
  ``QtCore`` / ``QtGui`` / ``QtWidgets``；其余模块（WebEngine、Qml、Quick、
  3D、Charts、Multimedia……）默认会被 PySide6 的 hook 一并收进来，体积以几十 MB 计。
* ``tkinter`` **必须保留**。``codex_config_tool.py`` 在模块顶层
  ``import tkinter as tk``，而 Qt 前端把整个模块当作库导入（84 个符号），所以
  即使 Qt 版自己一行 tkinter 都不用，打包时也必须带上 tkinter 与 tcl/tk。
  这是"共用业务逻辑"这个架构的直接代价，不是可以靠排除项省掉的。
"""

# 只排除确定不用的 Qt 模块。前端只 import QtCore / QtGui / QtWidgets，
# 其余都由 PySide6 的 hook 主动收集。保守起见不排除 QtNetwork / QtSvg /
# QtPrintSupport —— 它们是 QtWidgets 的可选依赖，删掉可能在运行期才报错。
QT_EXCLUDES = [
    # Web 引擎：单它一个就有上百 MB
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
    # QML / Quick 全家桶
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickTest",
    # 3D
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtQuick3D",
    # 图表 / 数据可视化
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    # 多媒体
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    # 其它用不到的
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    # 开发期工具
    "PySide6.scripts",
    "shiboken6_generator",
    # 项目里另有 Qt 前端之外的选择：不要连带打包 Tk 版以外的 GUI 栈
    "PyQt5",
    "PyQt6",
    "matplotlib",
    "numpy",
    "PIL",
]

a = Analysis(
    ["codex_config_qt.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets/donation_105.png", "assets"),
        ("assets/donation_210.png", "assets"),
        ("assets/app_icon.png", "assets"),
        ("assets/app_icon_title.png", "assets"),
        ("assets/app_icon_about.png", "assets"),
        ("assets/title_about.png", "assets"),
        ("assets/title_minimize.png", "assets"),
        ("assets/title_close.png", "assets"),
        ("assets/eye_smooth.png", "assets"),
        ("assets/eye_off_smooth.png", "assets"),
        ("assets/arkapi.png", "assets"),
        ("assets/jm2api.png", "assets"),
        ("assets/app_icon.ico", "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=QT_EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CodexConfigTool-Qt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # 见模块 docstring：UPX 压 Qt 运行时是已知崩溃源
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version="version_info.txt",
    icon=["assets/app_icon.ico"],
)
