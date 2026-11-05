from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.beijing import beijing_now

from app.core.database import Base


class OpenListServer(Base):
    """OpenList 服务器配置表（单服务器，最多一行启用）"""

    __tablename__ = "open_list_server"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    server_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="服务器地址（AList/OpenList API 地址）")
    token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="认证令牌（加密存储）")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=beijing_now, comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=beijing_now, onupdate=beijing_now, comment="更新时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    __table_args__ = (
        {"comment": "OpenList 服务器配置表"},
    )
