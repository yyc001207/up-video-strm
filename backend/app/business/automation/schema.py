"""自动化任务（模块 C）Pydantic 模型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_OPENLIST_MODES = ("incremental", "full", "strm_only")


class AutomationTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    upload_task_id: int = Field(gt=0)
    openlist_task_id: int = Field(gt=0)
    check_dir: str = Field(min_length=1, max_length=512)
    upload_concurrency: int = Field(default=2, ge=1, le=8)
    upload_retry_times: int = Field(default=3, ge=0, le=10)
    openlist_mode: str = Field(default="incremental")
    wait_interval_seconds: int = Field(default=15, ge=5, le=120)
    openlist_wait_timeout: int = Field(default=600, ge=60, le=3600)
    idle_wait_timeout: int = Field(default=600, ge=60, le=3600)
    stage_timeout: int = Field(default=3600, ge=60, le=7200)
    interval_seconds: int = Field(default=60, ge=10, le=3600)


class AutomationTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    upload_task_id: Optional[int] = Field(default=None, gt=0)
    openlist_task_id: Optional[int] = Field(default=None, gt=0)
    check_dir: Optional[str] = Field(default=None, min_length=1, max_length=512)
    upload_concurrency: Optional[int] = Field(default=None, ge=1, le=8)
    upload_retry_times: Optional[int] = Field(default=None, ge=0, le=10)
    openlist_mode: Optional[str] = None
    wait_interval_seconds: Optional[int] = Field(default=None, ge=5, le=120)
    openlist_wait_timeout: Optional[int] = Field(default=None, ge=60, le=3600)
    idle_wait_timeout: Optional[int] = Field(default=None, ge=60, le=3600)
    stage_timeout: Optional[int] = Field(default=None, ge=60, le=7200)
    interval_seconds: Optional[int] = Field(default=None, ge=10, le=3600)


class AutomationBatchDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class AutomationCheckDirRequest(BaseModel):
    """检测目录映射：新建时只传 upload_task_id + check_dir，编辑时可带 task_id。"""

    upload_task_id: int = Field(gt=0)
    check_dir: str = Field(default="", max_length=512)
    task_id: Optional[int] = None
