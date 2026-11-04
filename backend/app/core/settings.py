from pydantic_settings import BaseSettings

from app.core.paths import data_root, exe_dir, is_frozen

# 冻结运行时的可写数据根目录（%LOCALAPPDATA%\video-strm 或 VIDEO_STRM_HOME）；
# 源码运行时为 None，默认值保持相对当前工作目录，与改造前一致。
_data_root = data_root()


class Settings(BaseSettings):
    # SQLite（本地部署，无需 MySQL/Redis）
    sqlite_path: str = (
        str(_data_root / "data" / "video_strm.db") if _data_root else "./data/video_strm.db"
    )

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
