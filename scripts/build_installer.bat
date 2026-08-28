@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1"
if errorlevel 1 (
    echo.
    echo [FAILED] Installer build did not complete.
    exit /b 1
)

echo.
echo [SUCCESS] Portable EXE and installer are available in dist\.
exit /b 0
