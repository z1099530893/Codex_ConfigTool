param(
    [switch]$SkipBuild,
    [switch]$SkipQt,
    [string]$PythonPath = "",
    [string]$IsccPath = ""
)

# Release builder: produces the four assets that go on the GitHub release page.
#
#   dist\CodexConfigTool-Portable-v<ver>.exe      Tk  front end, portable
#   dist\CodexConfigTool-Setup-v<ver>.exe         Tk  front end, installer
#   dist\CodexConfigTool-Qt-Portable-v<ver>.exe   Qt  front end, portable
#   dist\CodexConfigTool-Qt-Setup-v<ver>.exe      Qt  front end, installer
#
# The two front ends share one AppId, one install directory and one AppMutex, so
# they are two front ends of one application rather than two applications. The
# installer definition therefore takes the EXE name and the output-name suffix as
# parameters instead of hardcoding the Tk one.
#
# NOTE ON ENCODING: keep this file pure ASCII. Windows PowerShell 5.1 decodes a .ps1
# as ANSI unless it starts with a UTF-8 BOM, so non-ASCII comments get misread and can
# break the parse with a confusing "unexpected token" error far from the real cause.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceFile = Join-Path $projectRoot "codex_config_tool.py"
$distDir = Join-Path $projectRoot "dist"
$installerScript = Join-Path $projectRoot "packaging\CodexConfigTool.iss"

$tkExe = Join-Path $distDir "CodexConfigTool.exe"
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
# --------------------------------------------------------------------------- #
if (-not $PythonPath) {
    $probe = "import tkinter, PyInstaller"
    if (-not $SkipQt) {
        $probe = "import tkinter, PyInstaller, PySide6"
    }
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
# Build the two EXEs.
# --------------------------------------------------------------------------- #
if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[STEP] Building the Tk front end..."
    & (Join-Path $PSScriptRoot "build.ps1") -PythonPath $PythonPath
    if ($LASTEXITCODE -ne 0) {
        throw "Tk EXE build failed."
    }

    if (-not $SkipQt) {
        Write-Host ""
        Write-Host "[STEP] Building the Qt front end..."
        & (Join-Path $PSScriptRoot "build_qt.ps1") -PythonPath $PythonPath
        if ($LASTEXITCODE -ne 0) {
            throw "Qt EXE build failed."
        }
    }
}

if (-not (Test-Path -LiteralPath $tkExe)) {
    throw "Tk EXE was not found: $tkExe"
}
if (-not $SkipQt -and -not (Test-Path -LiteralPath $qtExe)) {
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
# Portable assets: the EXEs are already single-file, so the portable release is a
# copy under the versioned name.
# --------------------------------------------------------------------------- #
$tkPortable = Join-Path $distDir "CodexConfigTool-Portable-v$appVersion.exe"
Copy-Item -LiteralPath $tkExe -Destination $tkPortable -Force
$produced = @($tkPortable)

if (-not $SkipQt) {
    $qtPortable = Join-Path $distDir "CodexConfigTool-Qt-Portable-v$appVersion.exe"
    Copy-Item -LiteralPath $qtExe -Destination $qtPortable -Force
    $produced += $qtPortable
}

# --------------------------------------------------------------------------- #
# Installers. The Qt pass overrides the EXE name and the output-name suffix; the
# AppId and install directory stay shared on purpose.
# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "[STEP] Building the Tk installer..."
& $IsccPath "/DMyAppVersion=$appVersion" $installerScript
if ($LASTEXITCODE -ne 0) {
    throw "Tk installer build failed."
}
$tkSetup = Join-Path $distDir "CodexConfigTool-Setup-v$appVersion.exe"
if (-not (Test-Path -LiteralPath $tkSetup)) {
    throw "Expected installer was not created: $tkSetup"
}
$produced += $tkSetup

if (-not $SkipQt) {
    Write-Host ""
    Write-Host "[STEP] Building the Qt installer..."
    & $IsccPath "/DMyAppVersion=$appVersion" "/DMyAppExeName=CodexConfigTool-Qt.exe" "/DMyAppOutputSuffix=-Qt" $installerScript
    if ($LASTEXITCODE -ne 0) {
        throw "Qt installer build failed."
    }
    $qtSetup = Join-Path $distDir "CodexConfigTool-Qt-Setup-v$appVersion.exe"
    if (-not (Test-Path -LiteralPath $qtSetup)) {
        throw "Expected installer was not created: $qtSetup"
    }
    $produced += $qtSetup
}

# --------------------------------------------------------------------------- #
# Report. The hashes go straight into the release notes, so print them rather than
# making the next person compute them by hand.
# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "[SUCCESS] Release assets for v$appVersion"
foreach ($path in $produced) {
    $item = Get-Item -LiteralPath $path
    $hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLower()
    Write-Host ("  {0}  {1} bytes  {2}" -f $item.Name, $item.Length, $hash)
}
