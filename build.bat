@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Codex Config Tool Builder

cd /d "%~dp0"

echo ========================================
echo   Codex Config Tool - Build
echo ========================================
echo.

if not exist "codex_config_tool.py" (
    echo [ERROR] codex_config_tool.py was not found.
    goto :failed
)

for %%F in ("赞赏.png" "app_icon.png" "app_icon_title.png" "app_icon_about.png" "eye_smooth.png" "eye_off_smooth.png" "app_icon.ico") do (
    if not exist "%%~F" (
        echo [ERROR] %%~F was not found.
        goto :failed
    )
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Install Python 3.10 or later, then run this file again.
    goto :failed
)

echo [INFO] Checking PyInstaller...
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [INFO] PyInstaller was not found. Installing it now...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        goto :failed
    )
)

tasklist /FI "IMAGENAME eq CodexConfigTool.exe" 2>nul | find /I "CodexConfigTool.exe" >nul
if not errorlevel 1 (
    echo [ERROR] CodexConfigTool.exe is currently running.
    echo Close the program, then run build.bat again.
    goto :failed
)

echo [INFO] Building CodexConfigTool.exe...
echo.
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon "app_icon.ico" --add-data "赞赏.png;." --add-data "app_icon.png;." --add-data "app_icon_title.png;." --add-data "app_icon_about.png;." --add-data "eye_smooth.png;." --add-data "eye_off_smooth.png;." --add-data "app_icon.ico;." --name "CodexConfigTool" "codex_config_tool.py"
if errorlevel 1 goto :failed

echo.
echo [SUCCESS] Build completed.
echo [OUTPUT] dist\CodexConfigTool.exe
echo.
if not defined CI (
    echo 按任意键继续...
    pause >nul
)
exit /b 0

:failed
echo.
echo [FAILED] Build did not complete. Review the message above.
echo.
if not defined CI (
    echo 按任意键继续...
    pause >nul
)
exit /b 1
