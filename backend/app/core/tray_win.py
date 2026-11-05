"""Windows 11 托盘图标可见性：让本程序的图标默认收进任务栏「^」折叠区。

Win11 会把新注册的托盘图标默认折叠进任务栏「^」里，是否常驻显示由
``HKCU\\Control Panel\\NotifyIconSettings\\<hash>`` 下的 ``IsPromoted`` 决定。
图标由 pystray 通过 Shell_NotifyIcon 注册后，Explorer 会为该可执行文件建立条目；
这里按 ``ExecutablePath`` 找到条目并写 ``IsPromoted``：

- 启动时写 ``0``（收进「^」），避免每次升级/重启后又被系统或旧逻辑置顶；
- 设置页「修复托盘图标」等显式操作可写 ``1`` 把图标固定到任务栏常驻区。

写入后通常在下一次注册（即下次启动应用）时生效；Explorer 未刷新时可重启资源管理器。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

BASE_KEY = r"Control Panel\NotifyIconSettings"


def _normalized(exe_path: str | None = None) -> str:
    return str(Path(exe_path or sys.executable).resolve()).lower()


def _find_entry(exe: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASE_KEY) as key:
            count = winreg.QueryInfoKey(key)[0]
            for index in range(count):
                name = winreg.EnumKey(key, index)
                try:
                    with winreg.OpenKey(key, name) as sub:
                        path, _ = winreg.QueryValueEx(sub, "ExecutablePath")
                except OSError:
                    continue
                if str(path).lower() == exe:
                    return name
    except OSError:
        return None
    return None


def is_promoted(exe_path: str | None = None) -> bool:
    import winreg

    name = _find_entry(_normalized(exe_path))
    if not name:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{BASE_KEY}\\{name}") as key:
            return bool(winreg.QueryValueEx(key, "IsPromoted")[0])
    except OSError:
        return False


def set_tray_icon_promoted(
    promoted: bool, exe_path: str | None = None, retries: int = 6, delay: float = 0.4
) -> bool:
    """把当前程序托盘图标的 ``IsPromoted`` 写为指定值；条目尚未生成时会短暂重试。"""
    if sys.platform != "win32":
        return False
    import winreg

    exe = _normalized(exe_path)
    for _ in range(max(1, retries)):
        name = _find_entry(exe)
        if name:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, f"{BASE_KEY}\\{name}", 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.SetValueEx(key, "IsPromoted", 0, winreg.REG_DWORD, 1 if promoted else 0)
                return True
            except OSError:
                return False
        time.sleep(delay)
    return False


def hide_tray_icon(exe_path: str | None = None, retries: int = 6, delay: float = 0.4) -> bool:
    """把托盘图标保留在 Win11 的「^」折叠区（默认行为）。"""
    return set_tray_icon_promoted(False, exe_path, retries, delay)


def promote_tray_icon(exe_path: str | None = None, retries: int = 6, delay: float = 0.4) -> bool:
    """把当前程序的托盘图标设为常驻显示（仅供设置页「修复托盘图标」等显式操作）。"""
    return set_tray_icon_promoted(True, exe_path, retries, delay)


def notify_icon_rect(hwnd: int, uid: int = 0) -> tuple[int, int, int, int] | None:
    """查询托盘图标在屏幕上的矩形；返回 None 表示未注册到系统托盘。

    ``Shell_NotifyIconGetRect`` 对未注册的 (hWnd, uID) 返回失败；
    坐标落在屏幕外（y 大于屏幕高度）说明图标位于 Win11 的折叠区「^」里。
    pystray 0.19.5 实际以 ``uID=0`` 注册（其 ``hID`` 字段名与结构体不符），故默认取 0。
    """
    import ctypes
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class NotifyIconIdentifier(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("guidItem", Guid),
        ]

    identifier = NotifyIconIdentifier(
        cbSize=ctypes.sizeof(NotifyIconIdentifier),
        hWnd=hwnd,
        uID=uid,
    )
    rect = wintypes.RECT()
    try:
        result = ctypes.windll.shell32.Shell_NotifyIconGetRect(
            ctypes.byref(identifier), ctypes.byref(rect)
        )
    except OSError:
        return None
    if result != 0:
        return None
    return rect.left, rect.top, rect.right, rect.bottom
