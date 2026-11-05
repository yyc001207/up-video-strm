"""桌面版偏好与开机自启。

- 偏好（启动时最小化到托盘、关闭窗口是否收进托盘）存数据目录的 ``desktop.json``，
  由启动器和 API 共同读写；不落数据库，避免污染业务数据。
- 开机自启读写 ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``，
  仅 Windows 桌面版可用（源码运行与网页访问一律视为不支持）。

命名迁移：正式版自启项值名由旧版 ``video-strm`` 改为 ``up-video-strm``。读取时新值优先，
旧值存在也视为已启用（旧版安装升级后无需重新勾选）；写入时同步删除旧值完成迁移。
测试版（``up-video-strm-test``）只读写自己的自启项，不迁移也不清理正式版的值。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.paths import (
    APP_DIR_NAME,
    APP_PROFILE,
    TEST_PROFILE,
    data_root,
    is_frozen,
)

PREFS_FILE = "desktop.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = APP_DIR_NAME
# 旧版自启项值名：仅正式版做一次性迁移；测试版不碰正式版的自启项
RUN_VALUES_LEGACY: tuple[str, ...] = () if APP_PROFILE == TEST_PROFILE else ("video-strm",)
DEFAULT_PREFS: dict[str, bool] = {
    "start_minimized": False,
    "close_to_tray": True,
}


def _home() -> Path:
    root = data_root()
    return root if root else Path.cwd()


def prefs_path() -> Path:
    return _home() / PREFS_FILE


def load_prefs() -> dict[str, bool]:
    """读取偏好；文件缺失或损坏时回退默认值。"""
    prefs = dict(DEFAULT_PREFS)
    try:
        raw = json.loads(prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return prefs
    if isinstance(raw, dict):
        for key in DEFAULT_PREFS:
            if isinstance(raw.get(key), bool):
                prefs[key] = raw[key]
    return prefs


def save_prefs(**updates: bool) -> dict[str, bool]:
    """合并写入偏好（只接受已知的布尔字段）。"""
    prefs = load_prefs()
    for key, value in updates.items():
        if key in DEFAULT_PREFS and isinstance(value, bool):
            prefs[key] = value
    path = prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    return prefs


def autostart_supported() -> bool:
    """仅 Windows 冻结运行（安装版/绿色版）支持写注册表自启。"""
    return sys.platform == "win32" and is_frozen()


def _exe_path() -> str:
    return str(Path(sys.executable).resolve())


def _run_value_enabled(value_name: str) -> bool:
    """HKCU Run 下指定值是否存在且非空。"""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except OSError:
        return False
    return bool(str(value).strip())


def _delete_run_value(value_name: str) -> None:
    """删除 HKCU Run 下指定值（不存在时静默忽略）。"""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, value_name)
    except OSError:
        pass


def is_autostart_enabled() -> bool:
    """新值优先；旧版自启值存在也视为已启用（升级后保持原有勾选状态）。"""
    if not autostart_supported():
        return False
    return any(_run_value_enabled(value) for value in (RUN_VALUE, *RUN_VALUES_LEGACY))


def set_autostart(enabled: bool) -> None:
    """写入/删除 HKCU Run 项；不支持的环境直接抛错由调用方转成 400。

    开启时写新值并删除旧值（完成旧版自启项迁移；测试版无旧值可迁移）；关闭时新值和旧值一并删除。
    """
    if not autostart_supported():
        raise RuntimeError("当前运行方式不支持开机自启")
    import winreg

    if enabled:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, f'"{_exe_path()}"')
        for legacy in RUN_VALUES_LEGACY:
            _delete_run_value(legacy)
    else:
        _delete_run_value(RUN_VALUE)
        for legacy in RUN_VALUES_LEGACY:
            _delete_run_value(legacy)


def refresh_autostart_path() -> None:
    """应用被移动/重装后，修正注册表里指向旧路径的自启项。

    已启用时重写为当前 exe 路径；旧版值名会在此同时迁移为新值名。
    """
    if not autostart_supported():
        return
    if is_autostart_enabled():
        try:
            set_autostart(True)
        except OSError:
            pass
