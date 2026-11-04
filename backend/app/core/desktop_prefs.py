"""桌面版偏好与开机自启。

- 偏好（启动时最小化到托盘、关闭窗口是否收进托盘）存数据目录的 ``desktop.json``，
  由启动器和 API 共同读写；不落数据库，避免影响 Docker 部署。
- 开机自启读写 ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``，
  仅 Windows 桌面版可用（源码运行与 Docker 一律视为不支持）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.paths import data_root, is_frozen

PREFS_FILE = "desktop.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "video-strm"
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


def is_autostart_enabled() -> bool:
    if not autostart_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
    except OSError:
        return False
    return bool(str(value).strip())


def set_autostart(enabled: bool) -> None:
    """写入/删除 HKCU Run 项；不支持的环境直接抛错由调用方转成 400。"""
    if not autostart_supported():
        raise RuntimeError("当前运行方式不支持开机自启")
    import winreg

    if enabled:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, f'"{_exe_path()}"')
    else:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, RUN_VALUE)
        except OSError:
            pass


def refresh_autostart_path() -> None:
    """应用被移动/重装后，修正注册表里指向旧路径的自启项。"""
    if not autostart_supported():
        return
    if is_autostart_enabled():
        try:
            set_autostart(True)
        except OSError:
            pass
