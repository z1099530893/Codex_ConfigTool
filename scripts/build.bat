@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Codex Config Tool Builder

cd /d "%~dp0.."

echo ========================================
echo   Codex Config Tool - Build
echo ========================================
echo.

if not exist "codex_config_tool.py" (
    echo [ERROR] codex_config_tool.py was not found.
    goto :failed
)

for %%F in ("assets\donation_105.png" "assets\donation_210.png" "assets\app_icon.png" "assets\app_icon_title.png" "assets\app_icon_about.png" "assets\title_about.png" "assets\title_minimize.png" "assets\title_close.png" "assets\eye_smooth.png" "assets\eye_off_smooth.png" "assets\arkapi.png" "assets\app_icon.ico" "version_info.txt") do (
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
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon "assets\app_icon.ico" --version-file "version_info.txt" --add-data "assets\donation_105.png;assets" --add-data "assets\donation_210.png;assets" --add-data "assets\app_icon.png;assets" --add-data "assets\app_icon_title.png;assets" --add-data "assets\app_icon_about.png;assets" --add-data "assets\title_about.png;assets" --add-data "assets\title_minimize.png;assets" --add-data "assets\title_close.png;assets" --add-data "assets\eye_smooth.png;assets" --add-data "assets\eye_off_smooth.png;assets" --add-data "assets\arkapi.png;assets" --add-data "assets\app_icon.ico;assets" --name "CodexConfigTool" "codex_config_tool.py"
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
