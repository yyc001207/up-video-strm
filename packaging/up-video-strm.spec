# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

正式版：``dist/up-video-strm/``（内含 up-video-strm.exe 与 _internal 依赖目录）。
测试版（``UP_STRM_BUILD_PROFILE=test``）：``dist/up-video-strm-test/``。

构建时会把构建配置写入 ``build/build_profile.json`` 并打包进资源根目录
（onedir 为 ``_internal``），运行时由 ``app/core/paths.py`` 读取，用于区分
正式版 / 测试版的数据目录、单实例与自启项。

前端产物需先就位：``backend/frontend/dist``（由 ``packaging/build.ps1`` 自动构建并复制）。
"""

import json
import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve()  # packaging/
PROJECT = ROOT.parent  # 仓库根目录
ENTRY = PROJECT / "backend" / "run.py"
FRONTEND_DIST = PROJECT / "backend" / "frontend" / "dist"

# 构建配置：prod（正式版，默认）/ test（测试版，由 packaging/build-test.ps1 传入）
PROFILE = os.environ.get("UP_STRM_BUILD_PROFILE", "prod").strip().lower()
if PROFILE not in ("prod", "test"):
    raise SystemExit(f"未知构建配置 UP_STRM_BUILD_PROFILE={PROFILE!r}（仅支持 prod / test）")
APP_NAME = "up-video-strm-test" if PROFILE == "test" else "up-video-strm"

# 构建标记文件：随包分发，运行时据此确定应用身份
PROFILE_MARKER = PROJECT / "build" / "build_profile.json"
PROFILE_MARKER.parent.mkdir(parents=True, exist_ok=True)
PROFILE_MARKER.write_text(
    json.dumps({"profile": PROFILE}, ensure_ascii=False), encoding="utf-8"
)

if not (FRONTEND_DIST / "index.html").is_file():
    raise SystemExit(
        f"缺少前端产物 {FRONTEND_DIST}：请先执行 npm run build，"
        "或直接用 packaging/build.ps1 一键构建"
    )

# uvicorn 通过字符串动态加载协议/生命周期实现，静态分析发现不了，需显式声明
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "aiosqlite",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
    # 原生窗口（pywebview + WebView2）：平台后端由运行时按需导入，静态分析发现不了
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr",
    "clr_loader",
    # 系统托盘
    "pystray",
    "pystray._win32",
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(PROJECT / "backend")],
    binaries=[],
    # 前端产物打包进 _internal/frontend/dist，由 app/main.py 通过 sys._MEIPASS 定位；
    # build_profile.json 打包到资源根目录，由 app/core/paths.py 读取
    datas=[(str(FRONTEND_DIST), "frontend/dist"), (str(PROFILE_MARKER), ".")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 无控制台窗口：GUI 进程，日志写数据目录 logs/app.log
    console=False,
    icon=str(ROOT / "app.ico"),
    version=str(ROOT / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
