"""上传管理：上传任务模型。

任务绑定本地目录与 123 云盘目标目录，指定季数与「源起始集号」，
上传文件名统一由重命名规则渲染为 ``SxxExx.ext``。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.beijing import beijing_now

from app.core.database import Base


class UploadTask(Base):
    """上传任务配置表。"""

    __tablename__ = "upload_task"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    local_dir: Mapped[str] = mapped_column(String(1024), nullable=False, comment="本地待上传目录")
    remote_dir: Mapped[str] = mapped_column(String(1024), nullable=False, comment="123 云盘目标目录（以 / 开头）")
    season: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="输出季数")
    start_episode: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="源起始集号：源文件最小集号映射为输出第 1 集"
    )
    rename_rule_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="重命名规则 ID（NULL 使用默认模板）"
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, comment="创建时间"
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, onupdate=beijing_now, comment="更新时间"
    )

    __table_args__ = ({"comment": "上传任务配置表"},)
