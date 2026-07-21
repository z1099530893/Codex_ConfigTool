$ErrorActionPreference = "Stop"

$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($pyinstaller) {
    & $pyinstaller.Source --noconfirm --onefile --windowed --add-data "赞赏.png;." --name "CodexConfigTool" codex_config_tool.py
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python was not found. Install Python and PyInstaller first."
}

& $python.Source -m PyInstaller --noconfirm --onefile --windowed --add-data "赞赏.png;." --name "CodexConfigTool" codex_config_tool.py
