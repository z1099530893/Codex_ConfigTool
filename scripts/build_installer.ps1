param(
    [switch]$SkipPortableBuild,
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceFile = Join-Path $projectRoot "codex_config_tool.py"
$distDir = Join-Path $projectRoot "dist"
$sourceExe = Join-Path $distDir "CodexConfigTool.exe"
$installerScript = Join-Path $projectRoot "packaging\CodexConfigTool.iss"

if (-not $SkipPortableBuild) {
    & (Join-Path $PSScriptRoot "build.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Portable EXE build failed."
    }
}

if (-not (Test-Path -LiteralPath $sourceExe)) {
    throw "Portable EXE was not found: $sourceExe"
}

$versionMatch = Select-String -LiteralPath $sourceFile -Pattern '^APP_VERSION\s*=\s*"(?<version>\d+\.\d+\.\d+)"$'
if (-not $versionMatch -or $versionMatch.Matches.Count -ne 1) {
    throw "APP_VERSION could not be read from codex_config_tool.py."
}
$appVersion = $versionMatch.Matches[0].Groups["version"].Value

$portableOutput = Join-Path $distDir "CodexConfigTool-Portable-v$appVersion.exe"
Copy-Item -LiteralPath $sourceExe -Destination $portableOutput -Force

if (-not $IsccPath) {
    $isccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($isccCommand) {
        $IsccPath = $isccCommand.Source
    }
}

if (-not $IsccPath) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    if ($candidates) {
        $IsccPath = $candidates[0]
    }
}

if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) {
    throw "Inno Setup 6 was not found. Install it, or pass -IsccPath with the full path to ISCC.exe."
}

& $IsccPath "/DMyAppVersion=$appVersion" $installerScript
if ($LASTEXITCODE -ne 0) {
    throw "Installer build failed."
}

$installerOutput = Join-Path $distDir "CodexConfigTool-Setup-v$appVersion.exe"
if (-not (Test-Path -LiteralPath $installerOutput)) {
    throw "Expected installer was not created: $installerOutput"
}

Write-Host "[SUCCESS] Portable: $portableOutput"
Write-Host "[SUCCESS] Installer: $installerOutput"
