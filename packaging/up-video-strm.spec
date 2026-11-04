# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

产物：``dist/up-video-strm/``（内含 up-video-strm.exe 与 _internal 依赖目录），
再由 ``packaging/installer.iss`` 封装成 ``setup.exe`` 安装包。

前端产物需先就位：``backend/frontend/dist``（由 ``packaging/build.ps1`` 自动构建并复制）。
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve()  # packaging/
PROJECT = ROOT.parent  # 仓库根目录
ENTRY = PROJECT / "backend" / "run.py"
FRONTEND_DIST = PROJECT / "backend" / "frontend" / "dist"

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
    # 前端产物打包进 _internal/frontend/dist，由 app/main.py 通过 sys._MEIPASS 定位
    datas=[(str(FRONTEND_DIST), "frontend/dist")],
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
    name="up-video-strm",
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
    name="up-video-strm",
)
