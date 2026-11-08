"""本地改名接口数据模型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RenameScanRequest(BaseModel):
    path: str = Field(default="", description="本机文件夹路径")


class RenameEntry(BaseModel):
    folder: str = Field(default="", description="文件所在文件夹（扫描结果原样回传）")
    name: str = Field(default="", description="原文件名（扫描结果原样回传）")
    new_name: Optional[str] = Field(default=None, description="自定义目标名；留空使用自动计算值")
    target_folder: Optional[str] = Field(default=None, description="目标文件夹（分季移动）；留空原地改名")


class RenameRequest(BaseModel):
    root: str = Field(default="", description="扫描根目录")
    entries: list[RenameEntry] = Field(default_factory=list)
    conflict_mode: str = Field(default="skip", description="skip / overwrite / autonum")
    keep_lang: bool = True
