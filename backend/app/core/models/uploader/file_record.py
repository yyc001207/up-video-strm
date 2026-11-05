"""上传管理：文件粒度执行记录模型。

每个待上传文件在「预上传清单」阶段落一条记录，后续阶段更新状态与远端信息，
用于执行详情页与历史追溯（覆盖时记录被替换的旧 fileId）。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.beijing import beijing_now

from app.core.database import Base


class UploadFileRecord(Base):
    """上传文件记录表。"""

    __tablename__ = "upload_file_record"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    execution_id: Mapped[int] = mapped_column(
        ForeignKey("upload_execution.id"), nullable=False, comment="关联执行记录 ID"
    )
    local_path: Mapped[str] = mapped_column(String(1024), nullable=False, comment="本地文件完整路径")
    remote_name: Mapped[str] = mapped_column(String(512), nullable=False, comment="重命名后的远端文件名")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="文件大小（字节）")
    md5: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="文件 MD5（etag）")
    status: Mapped[str] = mapped_column(
        Enum("pending", "uploading", "success", "skipped", "failed", name="upload_file_record_status"),
        nullable=False,
        default="pending",
        comment="文件状态",
    )
    phase: Mapped[str] = mapped_column(
        String(32), nullable=False, default="scan", comment="所处阶段：scan/rename/list/check/upload"
    )
    reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="跳过/失败原因")
    remote_file_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="上传成功后的云端 fileId")
    replaced_file_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="覆盖策略下被替换的旧 fileId"
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, comment="创建时间"
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, onupdate=beijing_now, comment="更新时间"
    )

    execution: Mapped["UploadExecution"] = relationship("UploadExecution", back_populates="records")

    __table_args__ = (
        Index("idx_upload_file_record_execution", "execution_id"),
        {"comment": "上传文件记录表"},
    )
