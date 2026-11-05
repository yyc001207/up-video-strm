"""自动化任务：把 A/B 执行的日志镜像进当前轮次的自动化日志（阶段④ 修复）。

自动化触发 A/B 时，A/B 的详细日志本来各写各的文件与 WS 通道；本模块按行增量
读取这些日志文件，转写到自动化 Logger 中，使「自动化任务 · 实时日志 / 任务历史
日志」能看到完整的 A/B 执行过程（前缀 ``[A#12]`` / ``[B#7]`` 标注来源与执行 ID）。

实现为文件尾随，而不是侵入 A/B 引擎：A/B 日志文件格式固定为
``[YYYY-MM-DD HH:MM:SS] [LEVEL] message``，尾随读取后还原 level 与消息，避免
自动化日志里叠加两层时间戳。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Optional

from app.business.automation.execution_logger import AutomationLogger

#: 尾随读取间隔（秒）
RELAY_INTERVAL_SECONDS = 0.8
#: A/B 日志行：``[2026-11-06 06:07:36] [INFO] message``
_LINE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*\[(\w+)\]\s?(.*)$")


class ExecutionLogRelay:
    """尾随一个 A/B 日志文件并转写到自动化日志。"""

    def __init__(self, logger: AutomationLogger, prefix: str):
        self._logger = logger
        self._prefix = prefix
        self._path: Optional[Path] = None
        self._offset = 0
        self._stopped = asyncio.Event()

    def set_path(self, path: Optional[str]) -> None:
        """由轮询结果提供日志文件路径（只需首次非空时设置）。"""
        if self._path is None and path:
            self._path = Path(path)

    def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        while True:
            await self._drain()
            if self._stopped.is_set():
                await self._drain()
                return
            await asyncio.sleep(RELAY_INTERVAL_SECONDS)

    async def _drain(self) -> None:
        path = self._path
        if path is None or not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self._offset)
                lines = fh.readlines()
                self._offset = fh.tell()
        except OSError:  # pragma: no cover - 文件被占用/删除时跳过
            return
        for line in lines:
            text = line.rstrip("\r\n")
            if not text:
                continue
            match = _LINE_RE.match(text)
            if match:
                level = match.group(2).lower()
                message = match.group(3)
            else:
                level = "info"
                message = text
            await self._logger.log(level, f"[{self._prefix}] {message}")
