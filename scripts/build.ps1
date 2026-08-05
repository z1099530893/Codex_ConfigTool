$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$assets = Join-Path $projectRoot "assets"
$donationThumbnail = Join-Path $assets "donation_105.png"
$donationDialog = Join-Path $assets "donation_210.png"

$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($pyinstaller) {
    & $pyinstaller.Source --noconfirm --onefile --windowed --icon (Join-Path $assets "app_icon.ico") --version-file "version_info.txt" --add-data "$donationThumbnail;assets" --add-data "$donationDialog;assets" --add-data ((Join-Path $assets "app_icon.png") + ";assets") --add-data ((Join-Path $assets "app_icon_title.png") + ";assets") --add-data ((Join-Path $assets "app_icon_about.png") + ";assets") --add-data ((Join-Path $assets "title_about.png") + ";assets") --add-data ((Join-Path $assets "title_minimize.png") + ";assets") --add-data ((Join-Path $assets "title_close.png") + ";assets") --add-data ((Join-Path $assets "eye_smooth.png") + ";assets") --add-data ((Join-Path $assets "eye_off_smooth.png") + ";assets") --add-data ((Join-Path $assets "app_icon.ico") + ";assets") --name "CodexConfigTool" codex_config_tool.py
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python was not found. Install Python and PyInstaller first."
}

& $python.Source -m PyInstaller --noconfirm --onefile --windowed --icon (Join-Path $assets "app_icon.ico") --version-file "version_info.txt" --add-data "$donationThumbnail;assets" --add-data "$donationDialog;assets" --add-data ((Join-Path $assets "app_icon.png") + ";assets") --add-data ((Join-Path $assets "app_icon_title.png") + ";assets") --add-data ((Join-Path $assets "app_icon_about.png") + ";assets") --add-data ((Join-Path $assets "title_about.png") + ";assets") --add-data ((Join-Path $assets "title_minimize.png") + ";assets") --add-data ((Join-Path $assets "title_close.png") + ";assets") --add-data ((Join-Path $assets "eye_smooth.png") + ";assets") --add-data ((Join-Path $assets "eye_off_smooth.png") + ";assets") --add-data ((Join-Path $assets "app_icon.ico") + ";assets") --name "CodexConfigTool" codex_config_tool.py
