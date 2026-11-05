from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class UploadPlatformConfig(Base):
    """123 云盘开放平台配置（单行表，凭据加密存储）。"""

    __tablename__ = "upload_platform_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    client_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="开放平台 clientID")
    client_secret: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True, comment="clientSecret（DPAPI 加密）")
    access_token: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True, comment="access_token（DPAPI 加密）")
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="access_token 过期时间"
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    __table_args__ = ({"comment": "123 云盘开放平台配置表"},)
