$ErrorActionPreference = "Stop"
$donationImage = ([string][char]0x8D5E) + ([char]0x8D4F) + ".png"

$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($pyinstaller) {
    & $pyinstaller.Source --noconfirm --onefile --windowed --icon "app_icon.ico" --add-data "$donationImage;." --add-data "app_icon.png;." --add-data "app_icon_title.png;." --add-data "app_icon_about.png;." --add-data "eye_smooth.png;." --add-data "eye_off_smooth.png;." --add-data "app_icon.ico;." --name "CodexConfigTool" codex_config_tool.py
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python was not found. Install Python and PyInstaller first."
}

& $python.Source -m PyInstaller --noconfirm --onefile --windowed --icon "app_icon.ico" --add-data "$donationImage;." --add-data "app_icon.png;." --add-data "app_icon_title.png;." --add-data "app_icon_about.png;." --add-data "eye_smooth.png;." --add-data "eye_off_smooth.png;." --add-data "app_icon.ico;." --name "CodexConfigTool" codex_config_tool.py
