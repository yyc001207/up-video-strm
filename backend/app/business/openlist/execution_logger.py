"""单次执行的日志通道：把生成器日志转发到 WebSocket + 追加到日志文件。

STRMGenerator/OpenListAPI 使用标准 logging；本模块提供一个 logging.Handler，
将每条记录放入 ``asyncio.Queue``，由 ``LogPump`` 协程消费：广播 WS 帧、
追加到本次执行的日志文件、推送进度。日志只写文件，不再写入数据库。
队列有界，满了丢弃最旧以保证日志推送永不阻塞生成器。
"""

import logging
import time
from datetime import datetime
from typing import Dict, Optional

from app.core.beijing import BEIJING_TZ
from app.websocket.manager import ws_manager

STOP = object()

_LEVEL_MAP = {"debug": "info", "info": "info", "warning": "warn", "warn": "warn", "error": "error", "critical": "error"}


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
            message = record.getMessage()
            item = (time.time(), map_level(record.levelname), message)
            try:
                self.queue.put_nowait(item)
            except Exception:
                self.dropped += 1
        except Exception:
            pass


class LogPump:
    """消费队列：广播 WS 帧、追加日志文件、推送进度（日志只写文件，不落库）。"""

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
        self.last_progress_frame: Optional[str] = None

    async def broadcast(self, message: dict):
        try:
            await ws_manager.broadcast(self.execution_id, message)
        except Exception:
            pass

    def _progress_frame(self) -> dict:
        return {
            "type": "progress",
            "data": {
                "totalVideos": self.progress.get("totalVideos", 0),
                "successVideos": self.progress.get("successVideos", 0),
                "totalSubtitles": self.progress.get("totalSubtitles", 0),
                "successSubtitles": self.progress.get("successSubtitles", 0),
            },
        }

    async def maybe_progress(self):
        frame = self._progress_frame()
        key = frame["data"]
        if key != self.last_progress_frame:
            self.last_progress_frame = key
            await self.broadcast(frame)

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
        """执行结束/取消/失败时推送最终状态帧。"""
        frame = {
            "type": "status",
            "status": status,
            "video_success_count": self.progress.get("successVideos", 0),
            "video_total_count": self.progress.get("totalVideos", 0),
            "subtitle_success_count": self.progress.get("successSubtitles", 0),
            "subtitle_total_count": self.progress.get("totalSubtitles", 0),
            **counts,
        }
        await self.broadcast(frame)
