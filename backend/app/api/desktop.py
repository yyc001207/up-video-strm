"""桌面版设置路由：开机自启 / 托盘偏好 / 数据目录。

这些能力依赖 Windows 桌面运行环境（注册表、资源管理器），
源码运行或网页访问时 ``is_desktop=false``，写操作统一返回 400。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import desktop_prefs
from app.core.exceptions import BadRequestException
from app.core.paths import data_root, is_frozen
from app.core.tray_win import promote_tray_icon
from app.utils.responses import success_response
from app.version import __version__

router = APIRouter()


class AutostartRequest(BaseModel):
    enabled: bool


class PreferencesRequest(BaseModel):
    start_minimized: Optional[bool] = None
    close_to_tray: Optional[bool] = None


def _info() -> dict:
    home = data_root() or Path.cwd()
    prefs = desktop_prefs.load_prefs()
    return {
        "is_desktop": is_frozen(),
        "version": __version__,
        "autostart_supported": desktop_prefs.autostart_supported(),
        "autostart": desktop_prefs.is_autostart_enabled(),
        "start_minimized": prefs["start_minimized"],
        "close_to_tray": prefs["close_to_tray"],
        "data_dir": str(home),
        "log_file": str(home / "logs" / "app.log"),
        "exe_path": sys.executable if is_frozen() else "",
    }


@router.get("/info", summary="桌面版信息与偏好")
async def get_info():
    return success_response(data=_info())


@router.post("/autostart", summary="设置开机自启")
async def update_autostart(data: AutostartRequest):
    if not desktop_prefs.autostart_supported():
        raise BadRequestException("仅 Windows 桌面版支持开机自启")
    try:
        desktop_prefs.set_autostart(data.enabled)
    except (OSError, RuntimeError) as exc:
        raise BadRequestException(f"设置开机自启失败：{exc}") from exc
    return success_response(data=_info())


@router.post("/preferences", summary="保存桌面版偏好（关闭到托盘立即生效，启动最小化重启后生效）")
async def update_preferences(data: PreferencesRequest):
    updates = {}
    if data.start_minimized is not None:
        updates["start_minimized"] = data.start_minimized
    if data.close_to_tray is not None:
        updates["close_to_tray"] = data.close_to_tray
    if updates:
        desktop_prefs.save_prefs(**updates)
    return success_response(data=_info())


@router.post("/fix-tray", summary="把托盘图标固定到任务栏（Win11 折叠区修复）")
async def fix_tray():
    if not is_frozen():
        raise BadRequestException("仅桌面版支持")
    promoted = promote_tray_icon()
    return success_response(data={"promoted": promoted})


@router.post("/open-taskbar-settings", summary="打开 Windows 任务栏设置（托盘图标开关）")
async def open_taskbar_settings():
    if not is_frozen():
        raise BadRequestException("仅桌面版支持")
    try:
        os.startfile("ms-settings:taskbar")  # noqa: S606  # 打开系统设置页
    except OSError as exc:
        raise BadRequestException(f"打开设置失败：{exc}") from exc
    return success_response(data={"opened": True})


@router.post("/open-data-dir", summary="在资源管理器中打开数据目录")
async def open_data_dir():
    if not is_frozen():
        raise BadRequestException("仅桌面版支持打开数据目录")
    home = data_root() or Path.cwd()
    try:
        os.startfile(str(home))  # noqa: S606  # 本地打开资源管理器
    except OSError as exc:
        raise BadRequestException(f"打开目录失败：{exc}") from exc
    return success_response(data={"path": str(home)})
