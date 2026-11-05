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


class UploadRenameRuleUpdate(BaseModel):
    """修改重命名规则：字段为 None 表示不修改。"""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    template: Optional[str] = Field(default=None, max_length=256)


class UploadRenameRuleResponse(BaseModel):
    id: int
    name: str
    template: str
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
