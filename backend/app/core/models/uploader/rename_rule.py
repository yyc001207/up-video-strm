"""上传管理：重命名规则模型。

规则只决定「输出文件名模板」，模板变量固定为 ``{season}`` / ``{episode}`` / ``{ext}``；
季数由任务指定，集数从源文件名解析后按「源起始集号」换算。
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.beijing import beijing_now

from app.core.database import Base


class UploadRenameRule(Base):
    """上传重命名规则表。"""

    __tablename__ = "upload_rename_rule"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="规则名称")
    template: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="文件名模板，如 S{season:02}E{episode:02}.{ext}"
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, comment="创建时间"
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, onupdate=beijing_now, comment="更新时间"
    )

    __table_args__ = ({"comment": "上传重命名规则表"},)
