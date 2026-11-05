"""自动化任务（模块 C）：任务配置模型。

一个自动化任务把模块 B（上传管理）的一个任务与模块 A（任务调度）的一个任务
串成固定链路；绑定关系在未删除任务内唯一（SQLite 部分唯一索引兜底）。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.beijing import beijing_now
from app.core.database import Base


class AutomationTask(Base):
    """自动化任务配置表。"""

    __tablename__ = "automation_task"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称，未删除任务内唯一")
    upload_task_id: Mapped[int] = mapped_column(
        ForeignKey("upload_task.id"), nullable=False, comment="绑定的上传任务（模块 B）ID"
    )
    openlist_task_id: Mapped[int] = mapped_column(
        ForeignKey("open_list_task.id"), nullable=False, comment="绑定的 STRM 任务（模块 A）ID"
    )
    upload_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2, comment="上传并发（1-8）")
    upload_retry_times: Mapped[int] = mapped_column(Integer, nullable=False, default=3, comment="上传重试次数（0-10）")
    openlist_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="incremental", comment="A 模式：incremental/full/strm_only"
    )
    check_dir: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="OpenList 校验目录（B remote_dir 的精确映射）"
    )
    wait_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15, comment="OpenList 校验等待退避基数（5-120 秒）"
    )
    openlist_wait_timeout: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600, comment="OpenList 可见性等待超时（秒）"
    )
    idle_wait_timeout: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600, comment="等待绑定任务空闲超时（秒）"
    )
    stage_timeout: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, comment="B/A 单阶段执行超时（秒）"
    )
    interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, comment="轮次间隔（10-3600 秒）"
    )
    pending_files: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="待校验文件 JSON 数组（remote_name 列表）"
    )
    pending_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="产生 pending 时的扫描指纹；A 成功清 pending 时提交为 scan_fingerprint"
    )
    scan_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="上次完整成功时的扫描指纹"
    )
    scan_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="指纹提交时间")
    last_round_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="最近一轮轮次号（历史清理后不重置）"
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="连续轮次失败次数（成功清零，达 3 终止）"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, comment="创建时间"
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, onupdate=beijing_now, comment="更新时间"
    )

    __table_args__ = (
        Index("idx_automation_task_is_deleted", "is_deleted"),
        # 绑定唯一：未删除任务内，一个 B/A 任务只能被一个自动化任务绑定
        Index(
            "uq_automation_task_upload_active",
            "upload_task_id",
            unique=True,
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "uq_automation_task_openlist_active",
            "openlist_task_id",
            unique=True,
            sqlite_where=text("is_deleted = 0"),
        ),
        Index(
            "uq_automation_task_name_active",
            "name",
            unique=True,
            sqlite_where=text("is_deleted = 0"),
        ),
    )
