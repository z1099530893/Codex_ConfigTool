@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Codex Config Tool - Qt Build
cd /d "%~dp0.."

echo ========================================
echo   Codex Config Tool - Qt (PySide6) Build
echo ========================================
echo.
echo [INFO] Building dist\CodexConfigTool-Qt.exe ...
echo [INFO] dist\CodexConfigTool.exe (Tk) will not be touched.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_qt.ps1" %*
if errorlevel 1 goto :failed

echo.
echo [SUCCESS] dist\CodexConfigTool-Qt.exe
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
