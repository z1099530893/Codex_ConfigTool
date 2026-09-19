param(
    [string]$PythonPath = ""
)

# Build the Tk single-file EXE: dist\CodexConfigTool.exe
#
# NOT part of the release flow since v1.5.0. The released product is the Qt front
# end, built by build_qt.ps1, because the Tk window cannot be made to stop flashing
# when it is restored from the taskbar (no backing store on a Tk top-level - see
# docs\ISSUE_LEDGER.md). This script is kept for two reasons: it produces the
# rollback artifact that build_qt.ps1 refuses to overwrite, and it is the way to
# reproduce the Tk front end for side-by-side measurement with prototypes\*.py.
# build_installer.ps1 does not call it.
#
# Interpreter selection matters here for the same reason it does in build_qt.ps1:
# this project's module imports tkinter at module level, and the interpreter that
# happens to be first on PATH on this machine has no tkinter at all. PyInstaller
# would then collect a build whose tkinter is missing, and the failure surfaces at
# run time rather than at build time. So the interpreter is verified, not assumed.
#
# NOTE ON ENCODING: keep this file pure ASCII. Windows PowerShell 5.1 decodes a .ps1
# as ANSI unless it starts with a UTF-8 BOM, so non-ASCII comments get misread and can
# break the parse with a confusing "unexpected token" error far from the real cause.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$assets = Join-Path $projectRoot "assets"
$donationThumbnail = Join-Path $assets "donation_105.png"
$donationDialog = Join-Path $assets "donation_210.png"

# The same set of data files as CodexConfigTool-Qt.spec carries. Kept as a list so
# the two invocation paths below cannot drift apart.
$dataFiles = @(
    "donation_105.png",
    "donation_210.png",
    "app_icon.png",
    "app_icon_title.png",
    "app_icon_about.png",
    "title_about.png",
    "title_minimize.png",
    "title_close.png",
    "eye_smooth.png",
    "eye_off_smooth.png",
    "arkapi.png",
    "jm2api.png",
    "app_icon.ico"
)

$pyinstallerArgs = @(
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--icon", (Join-Path $assets "app_icon.ico"),
    "--version-file", "version_info.txt"
)
foreach ($name in $dataFiles) {
    $pyinstallerArgs += @("--add-data", ((Join-Path $assets $name) + ";assets"))
}
$pyinstallerArgs += @("--name", "CodexConfigTool", "codex_config_tool.py")

if ($PythonPath) {
    $chosen = $PythonPath
    if (-not (Test-Path -LiteralPath $chosen)) {
        throw "The interpreter passed to -PythonPath does not exist: $chosen"
    }
    # Judged by exit code rather than by scraping stdout.
    & $chosen -c "import tkinter, PyInstaller" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "The interpreter passed to -PythonPath lacks tkinter or PyInstaller: $chosen"
    }
    Write-Host "[INFO] Interpreter: $chosen"
    & $chosen -c "import sys, tkinter; print('[INFO] Python', sys.version.split()[0], '| tk', tkinter.TkVersion)"
    & $chosen -m PyInstaller @pyinstallerArgs
    exit $LASTEXITCODE
}

$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($pyinstaller) {
    & $pyinstaller.Source @pyinstallerArgs
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python was not found. Install Python and PyInstaller first."
}

& $python.Source -m PyInstaller @pyinstallerArgs
