"""自动化任务：单轮运行的日志通道（阶段③）。

一轮 = 一个日志文件 ``automation_logs/automation_run_{run_id}.log``；日志行同时
以 WS 帧广播到 ``automation:{task_id}`` 频道，断线重连时由内存环形缓冲回放最近
200 帧。帧类型与 A/B 模块保持一致：``log`` / ``progress`` / ``status``，另外
``alert`` 用于异常终止通知（前端红点）。
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict

from app.core.beijing import BEIJING_TZ
from app.core.settings import settings
from app.websocket.manager import ws_manager

_LEVEL_MAP = {
    "debug": "info",
    "info": "info",
    "warning": "warn",
    "warn": "warn",
    "error": "error",
    "critical": "error",
}

#: 每个任务最近 200 帧（WS 重连回放）
TASK_RECENT: Dict[int, Deque[dict]] = {}


def channel(task_id: int) -> str:
    return f"automation:{task_id}"


def format_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def recent_frames(task_id: int, limit: int = 200) -> list[dict]:
    bucket = TASK_RECENT.get(task_id)
    if not bucket:
        return []
    return list(bucket)[-limit:]


def reset_recent() -> None:
    """测试辅助：清空回放缓冲。"""
    TASK_RECENT.clear()


class AutomationLogger:
    """一轮运行的日志写入器。"""

    def __init__(self, task_id: int, run_id: int):
        self.task_id = task_id
        self.run_id = run_id
        self.log_path: str = str(Path(settings.automation_log_dir) / f"automation_run_{run_id}.log")
        self._bucket = TASK_RECENT.setdefault(task_id, deque(maxlen=200))

    async def _emit(self, frame: dict, line: str | None = None) -> None:
        self._bucket.append(frame)
        try:
            await ws_manager.broadcast(channel(self.task_id), frame)
        except Exception:  # pragma: no cover - 广播失败不影响链路
            pass
        if line:
            try:
                Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:  # pragma: no cover - 磁盘异常不影响链路
                pass

    async def log(self, level: str, message: str) -> None:
        mapped = _LEVEL_MAP.get(level.lower(), "info")
        frame = {"type": "log", "level": mapped, "message": message, "ts": format_ts(time.time())}
        await self._emit(frame, f"[{frame['ts']}] [{level.upper()}] {message}")

    async def info(self, message: str) -> None:
        await self.log("info", message)

    async def warning(self, message: str) -> None:
        await self.log("warning", message)

    async def error(self, message: str) -> None:
        await self.log("error", message)

    async def progress(self, **data) -> None:
        await self._emit({"type": "progress", "data": data})

    async def status(self, **data) -> None:
        await self._emit({"type": "status", **data})

    async def alert(self, message: str, status: str = "fail") -> None:
        await self._emit({"type": "alert", "status": status, "message": message})


async def broadcast_notice(task_id: int, level: str, message: str) -> None:
    """无运行轮次的轻提示：仅广播 WS 一行（回放缓冲也记录），不落日志文件。

    用于「本轮无完整视频，忽略下载中文件 N 个」这类不属于某一轮的说明。
    """
    mapped = _LEVEL_MAP.get(level.lower(), "info")
    frame = {"type": "log", "level": mapped, "message": message, "ts": format_ts(time.time())}
    TASK_RECENT.setdefault(task_id, deque(maxlen=200)).append(frame)
    try:
        await ws_manager.broadcast(channel(task_id), frame)
    except Exception:  # pragma: no cover - 广播失败不影响链路
        pass
