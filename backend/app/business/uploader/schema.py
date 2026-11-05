"""上传管理模块 Pydantic 模型（阶段一：123 云盘凭据）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UploadPlatformConfigUpdate(BaseModel):
    """保存 123 云盘凭据：clientSecret 留空表示不修改已保存的密钥。"""

    model_config = ConfigDict(extra="forbid")

    client_id: Optional[str] = Field(default=None, max_length=128)
    client_secret: Optional[str] = Field(default=None, max_length=512)


class UploadPlatformConfigResponse(BaseModel):
    client_id: str = ""
    has_secret: bool = False
    secret_masked: str = ""
    token_status: str = "none"
    token_expires_at: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class UploadTestConnectionRequest(BaseModel):
    """测试连通性：clientID / clientSecret 留空时使用已保存的凭据。"""

    model_config = ConfigDict(extra="forbid")

    client_id: Optional[str] = Field(default=None, max_length=128)
    client_secret: Optional[str] = Field(default=None, max_length=512)


class UploadRenameRuleCreate(BaseModel):
    """新增重命名规则。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    template: Optional[str] = Field(default=None, max_length=256)
    episode_pattern: Optional[str] = Field(
        default=None,
        max_length=256,
        description="自定义集数提取正则（第 1 个分组为集号）；留空使用默认规则",
    )


class UploadRenameRuleUpdate(BaseModel):
    """修改重命名规则：字段为 None 表示不修改（episode_pattern 传空串表示清空）。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    template: Optional[str] = Field(default=None, max_length=256)
    episode_pattern: Optional[str] = Field(
        default=None,
        max_length=256,
        description="自定义集数提取正则（第 1 个分组为集号）；空串清空并恢复默认规则",
    )


class UploadRenameRuleResponse(BaseModel):
    id: int
    name: str
    template: str
    episode_pattern: Optional[str] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class UploadRenamePreviewRequest(BaseModel):
    """重命名预览：指定源文件名与任务参数，返回输出文件名（不落库）。"""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=512)
    season: int = Field(default=1, ge=1, le=99)
    start_episode: int = Field(default=1, ge=1, le=9999)
    rename_rule_id: Optional[int] = Field(default=None, ge=1)
    template: Optional[str] = Field(default=None, max_length=256)
    episode_pattern: Optional[str] = Field(
        default=None,
        max_length=256,
        description="自定义集数提取正则；留空时使用规则或默认规则",
    )


class UploadRenamePreviewResponse(BaseModel):
    matched: bool
    message: str = ""
    source_name: Optional[str] = None
    output_name: Optional[str] = None
    absolute_episode: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None


class UploadTaskCreate(BaseModel):
    """新增上传任务。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    local_dir: str = Field(min_length=1, max_length=1024)
    remote_dir: str = Field(min_length=1, max_length=1024)
    season: int = Field(default=1, ge=1, le=99)
    start_episode: int = Field(default=1, ge=1, le=9999)
    rename_rule_id: Optional[int] = Field(default=None, ge=1)


class UploadTaskUpdate(BaseModel):
    """修改上传任务：字段为 None 表示不修改。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    local_dir: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    remote_dir: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    season: Optional[int] = Field(default=None, ge=1, le=99)
    start_episode: Optional[int] = Field(default=None, ge=1, le=9999)
    rename_rule_id: Optional[int] = Field(default=None, ge=1)


class UploadTaskResponse(BaseModel):
    id: int
    name: str
    local_dir: str
    remote_dir: str
    season: int
    start_episode: int
    rename_rule_id: Optional[int] = None
    rename_rule_name: Optional[str] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class UploadRemoteDirItem(BaseModel):
    file_id: int
    file_name: str
    type: int = 1
    is_dir: bool = True


class UploadRemoteDirList(BaseModel):
    parent_id: int = 0
    path: str = "/"
    items: list[UploadRemoteDirItem] = []


# ---------------------------------------------------------------------------
# 执行 / 文件记录
# ---------------------------------------------------------------------------


class UploadExecutionCreate(BaseModel):
    """创建单任务执行记录（仅落库，不启动）。"""

    model_config = ConfigDict(extra="forbid")

    task_id: int = Field(ge=1)
    conflict_policy: str = Field(default="skip", pattern="^(skip|overwrite|suffix)$")
    concurrency: int = Field(default=2, ge=1, le=8)
    retry_times: int = Field(default=3, ge=0, le=10)
    dry_run: bool = False


class UploadExecutionBatchCreate(BaseModel):
    """批量创建执行记录（多任务，共享同一组执行参数）。"""

    model_config = ConfigDict(extra="forbid")

    task_ids: list[int] = Field(min_length=1)
    conflict_policy: str = Field(default="skip", pattern="^(skip|overwrite|suffix)$")
    concurrency: int = Field(default=2, ge=1, le=8)
    retry_times: int = Field(default=3, ge=0, le=10)
    dry_run: bool = False


class UploadExecutionStart(BaseModel):
    """启动已创建的执行记录。"""

    model_config = ConfigDict(extra="forbid")

    execution_id: int = Field(ge=1)
    task_id: int = Field(ge=1)


class UploadExecutionCancel(BaseModel):
    """取消正在运行的上传执行。"""

    model_config = ConfigDict(extra="forbid")

    execution_id: int = Field(ge=1)


class UploadFileRecordResponse(BaseModel):
    id: int
    execution_id: int
    local_path: str
    remote_name: str
    size: int = 0
    md5: str = ""
    status: str = "pending"
    phase: str = "scan"
    reason: Optional[str] = None
    remote_file_id: Optional[int] = None
    replaced_file_id: Optional[int] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class UploadBatchDeleteRequest(BaseModel):
    """批量删除请求：上传任务 / 重命名规则共用。"""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)


class UploadExecutionResponse(BaseModel):
    id: int
    task_id: int
    task_name: str
    local_dir: str
    remote_dir: str
    season: int
    start_episode: int
    rename_rule_id: Optional[int] = None
    template: str
    episode_pattern: Optional[str] = None
    conflict_policy: str
    concurrency: int
    retry_times: int
    dry_run: bool
    status: str
    file_total: int = 0
    file_success: int = 0
    file_skipped: int = 0
    file_failed: int = 0
    bytes_uploaded: int = 0
    duration_seconds: Optional[int] = None
    log_path: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    trigger_source: str = "manual"
    trigger_ref: Optional[str] = None
    trigger_name: Optional[str] = None
    started_time: Optional[datetime] = None
    finished_time: Optional[datetime] = None
    created_time: Optional[datetime] = None
