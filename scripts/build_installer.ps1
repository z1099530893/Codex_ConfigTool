param(
    [switch]$SkipBuild,
    [string]$PythonPath = "",
    [string]$IsccPath = ""
)

# Release builder: produces the two assets that go on the GitHub release page.
#
#   dist\CodexConfigTool-Portable-v<ver>.exe   portable, no install needed
#   dist\CodexConfigTool-Setup-v<ver>.exe      installer
#
# Both are built from the Qt (PySide6) front end. Since v1.5.0 that is the only
# front end that ships: the Tk front end cannot be made to stop flashing when the
# window is restored from the taskbar, so publishing it next to the fixed one only
# gives users a way to pick the broken build.
#
# The Tk view layer still lives in codex_config_tool.py, and it has to: that module
# is also the shared business logic that codex_config_qt.py imports. Retiring the Tk
# *release* is not the same as deleting the Tk *code*. scripts\build.ps1 still builds
# a Tk EXE for development and rollback purposes, but nothing here calls it.
#
# NOTE ON ENCODING: keep this file pure ASCII. Windows PowerShell 5.1 decodes a .ps1
# as ANSI unless it starts with a UTF-8 BOM, so non-ASCII comments get misread and can
# break the parse with a confusing "unexpected token" error far from the real cause.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceFile = Join-Path $projectRoot "codex_config_tool.py"
$distDir = Join-Path $projectRoot "dist"
$installerScript = Join-Path $projectRoot "packaging\CodexConfigTool.iss"

# Build artifact name. The installer renames it to CodexConfigTool.exe on install.
$qtExe = Join-Path $distDir "CodexConfigTool-Qt.exe"

# --------------------------------------------------------------------------- #
# Version: read from the single source of truth in the shared module.
# --------------------------------------------------------------------------- #
$versionMatch = Select-String -LiteralPath $sourceFile -Pattern '^APP_VERSION\s*=\s*"(?<version>\d+\.\d+\.\d+)"$'
if (-not $versionMatch -or $versionMatch.Matches.Count -ne 1) {
    throw "APP_VERSION could not be read from codex_config_tool.py."
}
$appVersion = $versionMatch.Matches[0].Groups["version"].Value
Write-Host "[INFO] Version: $appVersion"

# --------------------------------------------------------------------------- #
# Interpreter: pick one that can actually build. The interpreter first on PATH on
# this machine has no tkinter, and this project's shared module imports tkinter at
# module level, so an unverified choice produces a broken EXE rather than an error.
# All three of tkinter, PySide6 and PyInstaller must be present.
# --------------------------------------------------------------------------- #
if (-not $PythonPath) {
    $probe = "import tkinter, PyInstaller, PySide6"
    $candidates = @()
    $candidates += "C:\Program Files\Develop\Python\python.exe"
    foreach ($name in @("python.exe", "python3.exe")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found) {
            $candidates += $found.Source
        }
    }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        & $candidate -c $probe 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $PythonPath = $candidate
            break
        }
        Write-Host "[SKIP] $candidate (exit $LASTEXITCODE)"
    }
    if (-not $PythonPath) {
        throw "No interpreter satisfies the required imports. Pass -PythonPath with one that does."
    }
}
Write-Host "[INFO] Interpreter: $PythonPath"

# --------------------------------------------------------------------------- #
# Build the EXE.
# --------------------------------------------------------------------------- #
if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[STEP] Building the Qt front end..."
    & (Join-Path $PSScriptRoot "build_qt.ps1") -PythonPath $PythonPath
    if ($LASTEXITCODE -ne 0) {
        throw "Qt EXE build failed."
    }
}

if (-not (Test-Path -LiteralPath $qtExe)) {
    throw "Qt EXE was not found: $qtExe"
}

# --------------------------------------------------------------------------- #
# Locate ISCC.
# --------------------------------------------------------------------------- #
if (-not $IsccPath) {
    $isccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($isccCommand) {
        $IsccPath = $isccCommand.Source
    }
}

if (-not $IsccPath) {
    # Each root is guarded separately, for two reasons:
    #  * ${env:ProgramFiles(x86)} is not set in every session (32-bit PowerShell,
    #    some CI images), and with $ErrorActionPreference = "Stop" an empty path
    #    makes Join-Path throw instead of moving on to the next candidate.
    #  * a pipeline that yields a single match collapses to a string, so
    #    $candidates[0] would return the first *character* rather than the path.
    $isccRoots = @(
        @{ Root = $env:LOCALAPPDATA; Sub = "Programs\Inno Setup 6\ISCC.exe" },
        @{ Root = ${env:ProgramFiles(x86)}; Sub = "Inno Setup 6\ISCC.exe" },
        @{ Root = $env:ProgramFiles; Sub = "Inno Setup 6\ISCC.exe" }
    )
    foreach ($entry in $isccRoots) {
        if (-not $entry.Root) { continue }
        $candidate = Join-Path $entry.Root $entry.Sub
        if (Test-Path -LiteralPath $candidate) {
            $IsccPath = $candidate
            break
        }
    }
}

if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) {
    throw "Inno Setup 6 was not found. Install it, or pass -IsccPath with the full path to ISCC.exe."
}

# --------------------------------------------------------------------------- #
# Portable asset: the EXE is already single-file, so the portable release is a
# copy under the versioned name.
# --------------------------------------------------------------------------- #
$portable = Join-Path $distDir "CodexConfigTool-Portable-v$appVersion.exe"
Copy-Item -LiteralPath $qtExe -Destination $portable -Force
$produced = @($portable)

# --------------------------------------------------------------------------- #
# Installer. One ISCC pass; the EXE name and output name come from the .iss defaults.
# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "[STEP] Building the installer..."
& $IsccPath "/DMyAppVersion=$appVersion" $installerScript
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed."
}
$setup = Join-Path $distDir "CodexConfigTool-Setup-v$appVersion.exe"
if (-not (Test-Path -LiteralPath $setup)) {
    throw "Expected installer was not created: $setup"
}
$produced += $setup

# --------------------------------------------------------------------------- #
# Report. The hashes go straight into the release notes, so print them rather than
# making the next person compute them by hand. The same lines are also written to
# build\release-assets.txt: console scrollback is lost the moment the window closes,
# and a release note that quotes a hash nobody can re-derive is worse than no hash.
# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "[SUCCESS] Release assets for v$appVersion"
$report = @()
foreach ($path in $produced) {
    $item = Get-Item -LiteralPath $path
    $hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLower()
    $line = "  {0}  {1} bytes  {2}" -f $item.Name, $item.Length, $hash
    Write-Host $line
    $report += "$($item.Name)`n  size=$($item.Length)  hash=$hash"
}
$reportPath = Join-Path $projectRoot "build\release-assets.txt"
Set-Content -LiteralPath $reportPath -Value $report -Encoding UTF8
Write-Host "[INFO] Report written to $reportPath"
