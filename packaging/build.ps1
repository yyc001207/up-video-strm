# video-strm Windows packaging script (onedir + Inno Setup installer)
#
# Usage (from repo root or anywhere):
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipFrontend    # reuse existing dist
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipInstaller   # onedir only
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Dev             # dev: onedir only, keep staging
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Python C:\Python312\python.exe
#       (defaults to backend\.venv\Scripts\python.exe, then python on PATH; CI uses the latter)
#
# Outputs:
#   dist\video-strm-<version>-win-x64-setup.exe     Inno Setup installer (only deliverable)
#   PyInstaller onedir staging dir dist\video-strm is removed after packaging (-KeepStage keeps it)

param(
    [switch]$SkipFrontend,
    [switch]$SkipInstaller,
    # keep the PyInstaller onedir staging folder (dist\video-strm)
    [switch]$KeepStage,
    # dev mode: build onedir only and keep it (installers may be blocked by Smart App Control)
    [switch]$Dev,
    # python executable for PyInstaller; defaults to backend\.venv, then PATH
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$FrontendDist = Join-Path $FrontendDir "dist"
$BackendDist = Join-Path $ProjectRoot "backend\frontend\dist"
$SpecFile = Join-Path $PSScriptRoot "video-strm.spec"
$IssFile = Join-Path $PSScriptRoot "installer.iss"
$VersionFile = Join-Path $ProjectRoot "backend\app\version.py"
$VersionInfoFile = Join-Path $PSScriptRoot "version_info.txt"

# Version source of truth: backend\app\version.py (update via packaging\bump_version.py)
$VersionMatch = [regex]::Match((Get-Content $VersionFile -Raw), '__version__\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) { throw "cannot read __version__ from $VersionFile" }
$Version = $VersionMatch.Groups[1].Value

$PkgVersion = (Get-Content (Join-Path $FrontendDir "package.json") -Raw | ConvertFrom-Json).version
if ($PkgVersion -ne $Version) {
    throw "version mismatch: backend/app/version.py=$Version, frontend/package.json=$PkgVersion. Run: python packaging\bump_version.py <major|minor|patch>"
}
$LockPath = Join-Path $FrontendDir "package-lock.json"
$LockVersion = [regex]::Match((Get-Content $LockPath -Raw), '"version"\s*:\s*"([^"]+)"').Groups[1].Value
if ($LockVersion -ne $Version) {
    throw "version mismatch: backend/app/version.py=$Version, frontend/package-lock.json=$LockVersion. Run: python packaging\bump_version.py <major|minor|patch>"
}
if (-not (Get-Content $VersionInfoFile -Raw).Contains('"' + $Version + '"')) {
    throw "version mismatch: packaging/version_info.txt is not $Version. Run: python packaging\bump_version.py <major|minor|patch>"
}

if (-not $Python) {
    if (Test-Path $VenvPython) {
        $Python = $VenvPython
    }
    else {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $Python = $cmd.Source }
    }
}

if (-not $Python -or -not (Test-Path $Python)) {
    throw "Python not found: '$Python'. Create backend\.venv (pyenv 3.12) or pass -Python <path>."
}

if ($Dev) {
    $SkipInstaller = $true
    $KeepStage = $true
    Write-Host "==> Dev mode: onedir only, staging kept (run dist\video-strm\video-strm.exe)" -ForegroundColor Yellow
}

Write-Host "==> Version $Version" -ForegroundColor Cyan

if (-not $SkipFrontend) {
    Write-Host "==> Build frontend (npm run build)" -ForegroundColor Cyan
    Push-Location $FrontendDir
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "frontend build failed (exit $LASTEXITCODE)" }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $FrontendDist "index.html"))) {
    throw "frontend output missing: $FrontendDist (run without -SkipFrontend)"
}

Write-Host "==> Sync frontend output to backend\frontend\dist" -ForegroundColor Cyan
if (Test-Path $BackendDist) { Remove-Item $BackendDist -Recurse -Force }
New-Item -ItemType Directory -Path $BackendDist -Force | Out-Null
Copy-Item (Join-Path $FrontendDist "*") $BackendDist -Recurse -Force

Write-Host "==> PyInstaller build (onedir)" -ForegroundColor Cyan
Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean $SpecFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }
}
finally {
    Pop-Location
}

$ExePath = Join-Path $ProjectRoot "dist\video-strm\video-strm.exe"
if (-not (Test-Path $ExePath)) { throw "build output missing: $ExePath" }
Write-Host "==> Built $ExePath" -ForegroundColor Green

if ($SkipInstaller) {
    Write-Host "==> Installer skipped (-SkipInstaller); staging folder kept at dist\video-strm" -ForegroundColor Yellow
    exit 0
}

$Candidates = @()
if (${env:ProgramFiles(x86)}) { $Candidates += (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe") }
if ($env:ProgramFiles) { $Candidates += (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe") }
if ($env:LOCALAPPDATA) { $Candidates += (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe") }
$Iscc = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Iscc) {
    Write-Host "==> Inno Setup (ISCC.exe) not found, installer skipped" -ForegroundColor Yellow
    Write-Host "    Install Inno Setup 6, then rerun this script to produce setup.exe." -ForegroundColor Yellow
    Write-Host "    Staging folder dist\video-strm\ kept for manual use." -ForegroundColor Yellow
    exit 0
}

Write-Host "==> Build installer ($Iscc)" -ForegroundColor Cyan
& $Iscc "/DMyAppVersion=$Version" $IssFile
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed (exit $LASTEXITCODE)" }

$SetupPath = Join-Path $ProjectRoot "dist\video-strm-$Version-win-x64-setup.exe"
if (Test-Path $SetupPath) {
    Write-Host "==> Built $SetupPath" -ForegroundColor Green
}
else {
    Write-Host "==> Installer output dir: see OutputDir in packaging\installer.iss" -ForegroundColor Yellow
}

# Only the installer is delivered: clean staging dir and legacy portable zip
if (-not $KeepStage) {
    $StagePath = Join-Path $ProjectRoot "dist\video-strm"
    if (Test-Path $StagePath) {
        try {
            Remove-Item $StagePath -Recurse -Force -ErrorAction Stop
            Write-Host "==> Removed staging folder dist\video-strm (use -KeepStage to keep it)" -ForegroundColor DarkGray
        }
        catch {
            Write-Host "==> Could not remove dist\video-strm (program may be running): $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}
Get-ChildItem (Join-Path $ProjectRoot "dist") -Filter "*-portable.zip" -ErrorAction SilentlyContinue |
    ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "==> Removed legacy portable zip $($_.Name)" -ForegroundColor DarkGray
    }

# Keep only the installer just built
$CurrentSetup = Split-Path $SetupPath -Leaf
Get-ChildItem (Join-Path $ProjectRoot "dist") -Filter "video-strm-*-setup.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne $CurrentSetup } |
    ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "==> Removed old installer $($_.Name)" -ForegroundColor DarkGray
    }
