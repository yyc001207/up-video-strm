# up-video-strm test-build packaging script (onedir + Inno Setup installer)
#
# 测试版打包入口：内部以 -Profile test 调用 packaging\build.ps1，避免维护两份打包逻辑。
# 测试版与正式版完全隔离、可同时安装与运行：
#   exe            up-video-strm-test.exe
#   安装目录       %LOCALAPPDATA%\Programs\up-video-strm-test
#   数据目录       %LOCALAPPDATA%\up-video-strm-test（数据库/日志/STRM 输出/WebView 状态）
#   AppId/快捷方式/自启动项/单实例互斥体 均独立
#
# Usage (from repo root or anywhere):
#   powershell -ExecutionPolicy Bypass -File packaging\build-test.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build-test.ps1 -SkipFrontend   # 复用已有前端产物
#   powershell -ExecutionPolicy Bypass -File packaging\build-test.ps1 -SkipInstaller  # 只构建 onedir
#   powershell -ExecutionPolicy Bypass -File packaging\build-test.ps1 -Dev            # onedir only，保留中间目录
#
# Outputs:
#   dist\up-video-strm-test-<version>-win-x64-setup.exe   测试版安装包
#   dist\up-video-strm-test\                              中间目录（默认打包后清理，-KeepStage 保留）

param(
    [switch]$SkipFrontend,
    [switch]$SkipInstaller,
    [switch]$KeepStage,
    [switch]$Dev,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$Builder = Join-Path $PSScriptRoot "build.ps1"
if (-not (Test-Path $Builder)) { throw "build script not found: $Builder" }

# 透传调用方显式传入的参数，并强制 -Profile test
& $Builder -Profile test @PSBoundParameters
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
