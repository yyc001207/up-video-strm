"""运行时路径解析：统一区分「源码运行」与「PyInstaller 冻结运行」。

- 源码运行（``python run.py``）：行为与改造前完全一致，数据目录仍相对当前工作目录；
  构建配置恒为正式版（``prod``）。
- 冻结运行（打包后的 exe）：只读资源随包分发（onedir 在 ``_internal``，onefile 在
  ``_MEIPASS`` 临时目录），可写数据落在 ``%LOCALAPPDATA%\\<应用目录名>``，避免写入
  Program Files 触发权限错误，也避免 onefile 退出后临时目录被清空导致数据丢失。

应用身份由打包时注入的 ``build_profile.json`` 决定（源码运行为正式版）：

- 正式版 ``prod``：目录名 ``up-video-strm``；
- 测试版 ``test``：目录名 ``up-video-strm-test``，数据目录、单实例互斥体、开机自启项
  均与正式版隔离，两者可同时安装、同时运行。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 应用标识：正式版 / 测试版（同时作为 exe 名、安装目录名与数据目录名）
APP_NAME = "up-video-strm"
TEST_APP_NAME = "up-video-strm-test"
LEGACY_APP_DIR_NAME = "video-strm"
HOME_ENV = "UP_VIDEO_STRM_HOME"
LEGACY_HOME_ENV = "VIDEO_STRM_HOME"

# 构建配置：打包时由 PyInstaller spec 写入 ``build_profile.json`` 并随资源分发
PROFILE_FILE = "build_profile.json"
PROD_PROFILE = "prod"
TEST_PROFILE = "test"


def is_frozen() -> bool:
    """是否为 PyInstaller 打包后的运行态。"""
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    """exe 所在目录；源码运行返回 backend 目录。

    允许用户在 exe 同级放置 ``frontend/dist`` 覆盖内置前端产物，
    因此这里始终以真实可执行文件位置为准，而不是 ``__file__``。
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_dir() -> Path:
    """只读资源根目录：onefile 为 ``_MEIPASS``，onedir 为 ``_internal``，源码为 backend。"""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return exe_dir()
    return Path(__file__).resolve().parents[2]


def _read_build_profile(marker: Path) -> str:
    """读取打包标记文件中的构建配置；缺失或损坏时按正式版处理。"""
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PROD_PROFILE
    if isinstance(data, dict) and data.get("profile") == TEST_PROFILE:
        return TEST_PROFILE
    return PROD_PROFILE


def build_profile() -> str:
    """当前构建配置：``prod``（正式版）或 ``test``（测试版）。

    冻结运行时读取随包分发的 ``build_profile.json``（onedir 位于 ``_internal``，
    onefile 位于 ``_MEIPASS``）；源码运行恒为正式版。
    """
    if not is_frozen():
        return PROD_PROFILE
    return _read_build_profile(resource_dir() / PROFILE_FILE)


def app_dir_name(profile: str) -> str:
    """由构建配置推导应用目录名（同时用作 exe 名与安装目录名）。"""
    return TEST_APP_NAME if profile == TEST_PROFILE else APP_NAME


APP_PROFILE = build_profile()
APP_DIR_NAME = app_dir_name(APP_PROFILE)


def _home_override() -> Path | None:
    """显式指定的数据根目录：新环境变量优先，旧变量作为一次性兼容回退。"""
    override = os.environ.get(HOME_ENV) or os.environ.get(LEGACY_HOME_ENV)
    return Path(override).expanduser() if override else None


def _local_appdata_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    return Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"


def data_root() -> Path | None:
    """可写数据根目录。

    冻结运行（正式版）按以下顺序解析：

    1. ``UP_VIDEO_STRM_HOME``（显式覆盖，最优先）；
    2. 旧版环境变量 ``VIDEO_STRM_HOME``（旧配置一次性回退）；
    3. ``%LOCALAPPDATA%\\up-video-strm`` 已存在则直接使用；
    4. ``%LOCALAPPDATA%\\video-strm`` 已存在则沿用（旧版数据目录无感迁移：
       不搬移文件，旧数据库与旧配置继续可用）；
    5. 以上目录都不存在时返回新的 ``%LOCALAPPDATA%\\up-video-strm``（首次安装）。

    冻结运行（测试版）：显式覆盖仍最优先；否则直接返回
    ``%LOCALAPPDATA%\\up-video-strm-test``，**不**回退旧目录，保证测试数据与
    正式版完全隔离（首次启动为空数据目录）。

    源码运行：仅在显式设置 ``UP_VIDEO_STRM_HOME``（兼容旧 ``VIDEO_STRM_HOME``）时
    返回该目录，否则返回 ``None``，由 settings 保留原有的相对路径默认值。
    """
    override = _home_override()
    if not is_frozen():
        return override

    if override:
        return override
    base = _local_appdata_dir()
    current = base / APP_DIR_NAME
    if APP_PROFILE == TEST_PROFILE:
        return current
    if current.exists():
        return current
    legacy = base / LEGACY_APP_DIR_NAME
    if legacy.exists():
        return legacy
    return current
