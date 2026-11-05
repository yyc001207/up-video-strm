"""上传管理：执行记录模型。

每次执行在启动时固化任务参数（目录、季数、起始集号、模板、冲突策略、并发、
重试、试运行），保证历史可复现；文件粒度结果写入 ``upload_file_record``。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class UploadExecution(Base):
    """上传执行记录表。"""

    __tablename__ = "upload_execution"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    task_id: Mapped[int] = mapped_column(ForeignKey("upload_task.id"), nullable=False, comment="关联上传任务 ID")
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称快照")
    local_dir: Mapped[str] = mapped_column(String(1024), nullable=False, comment="本地目录快照")
    remote_dir: Mapped[str] = mapped_column(String(1024), nullable=False, comment="云端目录快照")
    season: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="输出季数快照")
    start_episode: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="源起始集号快照")
    rename_rule_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="命名规则 ID 快照")
    template: Mapped[str] = mapped_column(String(256), nullable=False, comment="命名模板快照")
    conflict_policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="skip", comment="冲突策略：skip/overwrite/suffix"
    )
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2, comment="并发数")
    retry_times: Mapped[int] = mapped_column(Integer, nullable=False, default=3, comment="单文件失败重试次数")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="试运行：仅生成清单")
    status: Mapped[str] = mapped_column(
        Enum("running", "success", "fail", "cancelled", name="upload_execution_status"),
        nullable=False,
        default="running",
        comment="执行状态",
    )
    file_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="待上传文件总数")
    file_success: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="上传成功数")
    file_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="跳过数")
    file_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="失败数")
    bytes_uploaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已上传字节数")
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="耗时（秒）")
    log_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="日志文件路径")
    started_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="开始执行时间")
    finished_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="执行结束时间")
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), comment="创建时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    task: Mapped["UploadTask"] = relationship("UploadTask")
    records: Mapped[list["UploadFileRecord"]] = relationship(
        "UploadFileRecord", back_populates="execution", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_upload_execution_task_id", "task_id"),
        Index("idx_upload_execution_status", "status"),
        Index("idx_upload_execution_started", "started_time"),
        {"comment": "上传执行记录表"},
    )
