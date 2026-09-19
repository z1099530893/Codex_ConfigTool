# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['codex_config_tool.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/donation_105.png', 'assets'), ('assets/donation_210.png', 'assets'), ('assets/app_icon.png', 'assets'), ('assets/app_icon_title.png', 'assets'), ('assets/app_icon_about.png', 'assets'), ('assets/title_about.png', 'assets'), ('assets/title_minimize.png', 'assets'), ('assets/title_close.png', 'assets'), ('assets/eye_smooth.png', 'assets'), ('assets/eye_off_smooth.png', 'assets'), ('assets/arkapi.png', 'assets'), ('assets/jm2api.png', 'assets'), ('assets/app_icon.ico', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='CodexConfigTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['assets/app_icon.ico'],
)
