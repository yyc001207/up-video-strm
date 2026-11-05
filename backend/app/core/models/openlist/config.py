from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.beijing import beijing_now

from app.core.database import Base


class OpenListConfig(Base):
    """OpenList 全局配置表"""

    __tablename__ = "open_list_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    server_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="服务器地址（AList/OpenList API 地址）")
    token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="认证令牌（加密存储）")
    video_formats: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, default="mp4,mkv,avi", comment="视频格式（逗号分隔）")
    subtitle_formats: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, default="srt,ass,vtt", comment="字幕格式（逗号分隔）")
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="同时执行任务个数")
    pause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=50, comment="间隔文件数量")
    pause_time: Mapped[str] = mapped_column(String(512), nullable=False, default="0,3,5", comment="暂停时间（秒，逗号分隔）")
    disable_ssl_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否禁用 SSL 证书验证（默认 False=校验，应对自签名证书时开启）")
    process_path_prefix: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default=None, comment="处理路径前缀（选择预设时自动拼接，默认空）")
    output_dir_prefix: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default=None, comment="输出目录前缀（选择预设时自动拼接，默认空）")
    output_root: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, default=None, comment="STRM/字幕输出根目录（留空=CWD/output；桌面版可指向媒体库绝对路径）")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=beijing_now, comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=beijing_now, onupdate=beijing_now, comment="更新时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    __table_args__ = (
        {"comment": "OpenList 全局配置表"},
    )
