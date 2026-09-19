<#
.SYNOPSIS
    Build the portable EXE for the Qt (PySide6) front end.

.DESCRIPTION
    Deliberate differences from scripts\build.ps1:

    * It uses CodexConfigTool-Qt.spec, entry point codex_config_qt.py, and produces
      dist\CodexConfigTool-Qt.exe - it does NOT overwrite dist\CodexConfigTool.exe.
      That file is the Tk build's rollback artifact and the input to
      build_installer.ps1, so both products have to coexist until the Qt build has
      been confirmed by hand.

    * It picks the interpreter explicitly. build.ps1 runs whatever `python` is on
      PATH; on this machine that is the managed interpreter, which has no tkinter
      and cannot run this project at all. The Qt build needs PySide6, tkinter AND
      PyInstaller in one interpreter, so every candidate is verified rather than
      trusting the first python on PATH.

    * It does not build an installer by itself. build_installer.ps1 calls this script
      and then runs ISCC twice, once per front end, producing all four release assets.

    NOTE ON ENCODING: keep this file pure ASCII. Windows PowerShell 5.1 decodes a
    .ps1 as ANSI unless it starts with a UTF-8 BOM, so non-ASCII comments (Chinese,
    for instance) get misread and can break the parse with a confusing "unexpected
    token" error far from the real cause. build_installer.ps1 is ASCII for the same
    reason. Put any non-English rationale in the docs, not here.

.EXAMPLE
    .\scripts\build_qt.ps1
    .\scripts\build_qt.ps1 -PythonPath "C:\Program Files\Develop\Python\python.exe"
#>
param(
    [string]$PythonPath = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$specFile = Join-Path $projectRoot "CodexConfigTool-Qt.spec"
$distExe = Join-Path $projectRoot "dist\CodexConfigTool-Qt.exe"
$tkExe = Join-Path $projectRoot "dist\CodexConfigTool.exe"

if (-not (Test-Path -LiteralPath $specFile)) {
    throw "Spec file not found: $specFile"
}

# The managed interpreter is a candidate too, but the import check below rejects it
# because it has no tkinter.
$candidates = @()
if ($PythonPath) {
    $candidates += $PythonPath
} else {
    $candidates += "C:\Program Files\Develop\Python\python.exe"
    foreach ($name in @("python.exe", "python3.exe")) {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found) {
            $candidates += $found.Source
        }
    }
}

# Judged by exit code rather than by scraping stdout: a successful import exits 0,
# and that is the one signal that does not depend on how output is captured.
# Kept on one line on purpose - a here-string's closing delimiter must sit at column
# zero, which is easy to break with an innocuous-looking edit later.
$probe = "import PySide6, tkinter, PyInstaller"

$chosen = ""
foreach ($candidate in $candidates) {
    if (-not (Test-Path -LiteralPath $candidate)) {
        continue
    }
    & $candidate -c $probe 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $chosen = $candidate
        break
    }
    Write-Host "[SKIP] $candidate (exit $LASTEXITCODE)"
}

if (-not $chosen) {
    throw "No interpreter has all of PySide6, tkinter and PyInstaller. Pass -PythonPath with one that does."
}

Write-Host "[INFO] Interpreter: $chosen"
& $chosen -c "import sys, PySide6, PySide6.QtCore as c; print('[INFO] Python', sys.version.split()[0], '| PySide6', PySide6.__version__, '| Qt', c.__version__)"

if ($Clean) {
    $buildDir = Join-Path $projectRoot "build\CodexConfigTool-Qt"
    if (Test-Path -LiteralPath $buildDir) {
        Remove-Item -LiteralPath $buildDir -Recurse -Force
        Write-Host "[INFO] Cleaned $buildDir"
    }
}

# Record the Tk artifact's hash so it can be re-checked after the build.
$tkExeBefore = ""
if (Test-Path -LiteralPath $tkExe) {
    $tkExeBefore = (Get-FileHash -LiteralPath $tkExe -Algorithm SHA256).Hash
}

& $chosen -m PyInstaller --noconfirm --distpath (Join-Path $projectRoot "dist") --workpath (Join-Path $projectRoot "build") $specFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed (exit $LASTEXITCODE)."
}

if (-not (Test-Path -LiteralPath $distExe)) {
    throw "Expected EXE was not created: $distExe"
}

# A guard, not a formality: not touching the Tk artifact is the whole reason this
# script exists separately from build.ps1.
if ($tkExeBefore) {
    $tkExeAfter = (Get-FileHash -LiteralPath $tkExe -Algorithm SHA256).Hash
    if ($tkExeAfter -ne $tkExeBefore) {
        throw "dist\CodexConfigTool.exe changed during the Qt build - that must never happen."
    }
    $prefix = $tkExeBefore.Substring(0, 8)
    Write-Host "[OK] dist\CodexConfigTool.exe untouched (sha256 $prefix...)"
}

$size = [math]::Round((Get-Item -LiteralPath $distExe).Length / 1MB, 1)
Write-Host "[SUCCESS] $distExe ($size MB)"
