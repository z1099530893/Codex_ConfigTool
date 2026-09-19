@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Codex Config Tool - Release Builder
cd /d "%~dp0.."

echo ========================================
echo   Codex Config Tool - Release Build
echo ========================================
echo.
echo [INFO] Building the two release assets (Qt front end only):
echo [INFO]   portable  - no install needed
echo [INFO]   installer - Start Menu shortcut + uninstaller
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1"
if errorlevel 1 goto :failed

echo.
echo [SUCCESS] Release assets were created:
echo [OUTPUT] %CD%\dist\CodexConfigTool-Portable-v*.exe
echo [OUTPUT] %CD%\dist\CodexConfigTool-Setup-v*.exe
echo [OUTPUT] %CD%\dist\CodexConfigTool-Qt-Portable-v*.exe
echo [OUTPUT] %CD%\dist\CodexConfigTool-Qt-Setup-v*.exe
goto :done

:failed
echo.
echo [FAILED] Build did not complete. Review the message above.
if not defined CI pause
exit /b 1

:done
echo.
if not defined CI (
    echo Press any key to close this window...
    pause >nul
)
exit /b 0
