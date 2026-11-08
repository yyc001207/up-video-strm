"""up-video-strm API：OpenList 任务调度独立服务（本地部署，无登录/无 Redis/MySQL）。"""

from contextlib import asynccontextmanager
import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.settings import settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.exceptions import UpVideoStrmException
from app.core.logger import logger
from app.core.paths import APP_DIR_NAME, exe_dir, is_frozen, resource_dir
from app.business.automation.retention import cleanup_once, daily_cleanup_loop
from app.business.execution_registry import clear as clear_execution_registry
from app.utils.responses import success_response
from app.api import automation, desktop, openlist, renamer, uploader
from app.version import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 进程重启后内存中的执行闸门不再可信，清空以免残留占位
    clear_execution_registry()
    # 自动化任务历史：进程启动清理一次，并注册每日定时清理
    try:
        async with AsyncSessionLocal() as db:
            await cleanup_once(db)
    except Exception as exc:  # noqa: BLE001  清理失败不阻塞启动
        logger.warning("启动清理自动化任务历史失败: %s", exc)
    cleanup_task = asyncio.create_task(daily_cleanup_loop(AsyncSessionLocal))
    try:
        yield
    finally:
        cleanup_task.cancel()


app = FastAPI(
    title=f"{APP_DIR_NAME} API",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    msg = first.get("msg", "参数错误")
    return JSONResponse(
        status_code=200,
        content={"code": 400, "msg": msg, "data": None},
    )


@app.exception_handler(UpVideoStrmException)
async def up_video_strm_exception_handler(request: Request, exc: UpVideoStrmException):
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "msg": exc.msg, "data": None},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # 记录完整堆栈，便于排查「接口报 500 但后台任务已启动」这类静默错误
    logger.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=200,
        content={"code": 500, "msg": "服务器内部错误", "data": None},
    )


app.include_router(openlist.router, prefix="/api/openlist", tags=["OpenList"])
app.include_router(uploader.router, prefix="/api/upload", tags=["Upload"])
app.include_router(automation.router, prefix="/api/automation", tags=["Automation"])
app.include_router(renamer.router, prefix="/api/renamer", tags=["Renamer"])
app.include_router(desktop.router, prefix="/api/desktop", tags=["Desktop"])


@app.get("/api/health")
async def health_check():
    return success_response(data={"status": "ok"})


# 前端构建产物目录：
# - 源码运行：backend/frontend/dist（backend/app/main.py → parents[1]）
# - 冻结运行：优先 exe 同级 frontend/dist（可不重新打包直接替换前端），
#   否则用随包分发的资源目录（onedir 为 _internal，onefile 为 _MEIPASS 临时目录）
def _resolve_dist_dir() -> Path:
    if is_frozen():
        candidates = [
            exe_dir() / "frontend" / "dist",
            resource_dir() / "frontend" / "dist",
        ]
    else:
        candidates = [Path(__file__).resolve().parents[1] / "frontend" / "dist"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


DIST_DIR = _resolve_dist_dir()


def mount_frontend() -> None:
    """存在前端构建产物时托管静态资源并做 SPA 回退；本地纯后端开发（未构建前端）时自动跳过。"""

    if not DIST_DIR.is_dir():
        return

    assets_dir = DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_file = DIST_DIR / "index.html"
    # 入口 HTML 不缓存：安装升级后必须重新拉取，否则 WebView2 可能沿用旧 index.html
    # 继续加载上一版本带哈希的旧 bundle，导致新页面/新模块看不到。
    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # API / 文档路由未命中时保持 404，不返回前端页面
        if full_path.startswith("api/") or full_path in {"docs", "redoc", "openapi.json"}:
            raise HTTPException(status_code=404, detail="Not Found")
        target = (DIST_DIR / full_path).resolve()
        if full_path and target.is_file() and target.is_relative_to(DIST_DIR.resolve()):
            if target == index_file.resolve():
                return FileResponse(target, headers=no_cache_headers)
            return FileResponse(target)
        if index_file.is_file():
            return FileResponse(index_file, headers=no_cache_headers)
        raise HTTPException(status_code=404, detail="Not Found")


mount_frontend()
