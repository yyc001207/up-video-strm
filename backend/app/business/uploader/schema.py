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
