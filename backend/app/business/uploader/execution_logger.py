"""上传管理：单次执行的日志通道（对齐 OpenList 模块）。

标准 logging → ``ExecutionLogHandler``（有界队列）→ ``UploadLogPump`` 协程
消费：广播 WebSocket 帧、追加日志文件、推送文件级进度。

帧格式与调度模块一致：``log`` / ``progress`` / ``status``。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, Optional

from app.core.beijing import BEIJING_TZ
from app.websocket.manager import ws_manager

STOP = object()

_LEVEL_MAP = {
    "debug": "info",
    "info": "info",
    "warning": "warn",
    "warn": "warn",
    "error": "error",
    "critical": "error",
}


def map_level(levelname: str) -> str:
    return _LEVEL_MAP.get(levelname.lower(), "info")


def format_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


class ExecutionLogHandler(logging.Handler):
    """同步 Handler：把日志记录写入 asyncio.Queue（有界，满了丢弃）。"""

    def __init__(self, queue, maxsize: int = 5000):
        super().__init__()
        self.queue = queue
        self.maxsize = maxsize
        self.dropped = 0

    def emit(self, record: logging.LogRecord):
        try:
            item = (time.time(), map_level(record.levelname), record.getMessage())
            try:
                self.queue.put_nowait(item)
            except Exception:
                self.dropped += 1
        except Exception:
            pass


class UploadLogPump:
    """消费队列：广播 WS 帧、追加日志文件、推送上传进度。"""

    def __init__(
        self,
        execution_id: int,
        queue,
        log_file_path: str,
        progress: Dict[str, int],
    ):
        self.execution_id = execution_id
        self.queue = queue
        self.log_file_path = log_file_path
        self.progress = progress
        self.last_progress_key: Optional[tuple] = None

    async def broadcast(self, message: dict):
        try:
            await ws_manager.broadcast(self.execution_id, message)
        except Exception:
            pass

    def _progress_frame(self) -> dict:
        return {
            "type": "progress",
            "data": {
                "total": self.progress.get("total", 0),
                "success": self.progress.get("success", 0),
                "skipped": self.progress.get("skipped", 0),
                "failed": self.progress.get("failed", 0),
                "bytesUploaded": self.progress.get("bytesUploaded", 0),
                "current": self.progress.get("current", ""),
            },
        }

    async def maybe_progress(self):
        key = (
            self.progress.get("total", 0),
            self.progress.get("success", 0),
            self.progress.get("skipped", 0),
            self.progress.get("failed", 0),
            self.progress.get("bytesUploaded", 0),
            self.progress.get("current", ""),
        )
        if key != self.last_progress_key:
            self.last_progress_key = key
            await self.broadcast(self._progress_frame())

    def _log_line(self, item) -> str:
        ts, level, message = item
        return f"[{format_ts(ts)}] [{level.upper()}] {message}"

    async def _append_file(self, line: str):
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    async def run(self):
        while True:
            item = await self.queue.get()
            if item is STOP:
                break
            ts, level, message = item
            await self.broadcast(
                {"type": "log", "level": level, "message": message, "ts": format_ts(ts)}
            )
            await self._append_file(self._log_line(item))
            await self.maybe_progress()
        await self.broadcast(self._progress_frame())

    async def stop(self):
        await self.queue.put(STOP)

    async def write_status(self, status: str, **counts):
        frame = {
            "type": "status",
            "status": status,
            "total": self.progress.get("total", 0),
            "success": self.progress.get("success", 0),
            "skipped": self.progress.get("skipped", 0),
            "failed": self.progress.get("failed", 0),
            "bytes_uploaded": self.progress.get("bytesUploaded", 0),
            **counts,
        }
        await self.broadcast(frame)
