"""自动化任务（模块 C）：运行历史模型（一轮链路的执行记录）。

生命周期 = 建 run → A 终态 / 用户停止 / 致命失败；轮次间隔不属于 run，
只在 ``/active`` 的任务运行态中体现。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.beijing import beijing_now
from app.core.database import Base


class AutomationRun(Base):
    """自动化任务单轮执行记录。"""

    __tablename__ = "automation_run"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    task_id: Mapped[int] = mapped_column(
        ForeignKey("automation_task.id"), nullable=False, comment="所属自动化任务 ID"
    )
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称快照")
    round_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="第几轮（建 run 时递增）")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", comment="运行状态：running/success/partial/fail/cancelled"
    )
    phase: Mapped[str] = mapped_column(
        String(32), nullable=False, default="waiting_idle", comment="当前阶段：waiting_idle 等 5 种"
    )
    upload_execution_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="本轮 B 执行 ID（补偿轮可为空）"
    )
    openlist_execution_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="本轮 A 执行 ID")
    new_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本轮 B 新上传成功文件数")
    pending_file_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本轮结束后仍待校验文件数"
    )
    checked_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已确认可见文件数")
    skipped_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本轮 B 上报跳过数")
    wait_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="OpenList 校验等待耗时（秒）")
    idle_wait_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="等待空闲耗时（秒）")
    missed_files: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="超时缺失文件 JSON 数组（最多 200 条）"
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="失败分类")
    error_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="失败原因（截断 500 字）")
    log_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="日志文件路径")
    started_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="本轮开始时间")
    finished_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="本轮结束时间")
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=beijing_now, comment="创建时间"
    )

    __table_args__ = (
        Index("idx_automation_run_task_started", "task_id", "started_time"),
        Index("idx_automation_run_status", "status"),
        Index("idx_automation_run_error_code", "error_code"),
    )
