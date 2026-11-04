from pathlib import Path

from pydantic_settings import BaseSettings

from app.core.paths import data_root, exe_dir, is_frozen

# 冻结运行时的可写数据根目录（%LOCALAPPDATA%\up-video-strm 或 UP_VIDEO_STRM_HOME）；
# 源码运行时为 None，默认值保持相对当前工作目录，与改造前一致。
_data_root = data_root()

# 默认 SQLite 文件名；旧版数据库文件名保留用于一次性兼容回退
_DB_NAME = "up_video_strm.db"
_LEGACY_DB_NAME = "video_strm.db"


def _default_db_path() -> str:
    """默认 SQLite 路径。

    优先使用新的 ``up_video_strm.db``；若同目录下新文件不存在而旧文件
    ``video_strm.db`` 存在，则沿用旧文件，避免升级后用户数据「消失」。
    冻结运行（数据目录）与源码运行（./data）两种情形规则一致。
    """
    if _data_root:
        base_dir = _data_root / "data"
        db_path = str(base_dir / _DB_NAME)
        legacy_path = str(base_dir / _LEGACY_DB_NAME)
    else:
        db_path = f"./data/{_DB_NAME}"
        legacy_path = f"./data/{_LEGACY_DB_NAME}"
    if not Path(db_path).exists() and Path(legacy_path).exists():
        return legacy_path
    return db_path


class Settings(BaseSettings):
    # SQLite（本地部署，无需 MySQL/Redis）
    sqlite_path: str = _default_db_path()

    # OpenList：执行日志文件目录（独立于数据库目录存放）
    openlist_log_dir: str = (
        str(_data_root / "openlist_logs") if _data_root else "./openlist_logs"
    )

    # CORS（本地开发前端默认 5173；本地部署可放宽为 * 或指定端口）
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        # 冻结运行：先读数据目录 .env，再读 exe 同级 .env（后者优先），方便用户覆盖配置；
        # 源码运行仍读 backend/.env
        env_file = (
            (str(_data_root / ".env"), str(exe_dir() / ".env"))
            if is_frozen() and _data_root
            else ".env"
        )
        case_sensitive = False


settings = Settings()
