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

if not exist "赞赏.png" (
    echo [ERROR] 赞赏.png was not found.
    goto :failed
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
python -m PyInstaller --noconfirm --clean --onefile --windowed --add-data "赞赏.png;." --name "CodexConfigTool" "codex_config_tool.py"
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
