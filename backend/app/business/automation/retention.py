"""自动化任务历史保留清理（阶段 ①）。

保留策略（设计文档 §3.4）：
- ``automation_run``：保留最近 90 天，且每个自动化任务最多 1000 条；
- 运行日志：保留 90 天，且每个任务最多 200 个文件。

清理时机：进程启动、自动化任务启动、每日定时后台任务（main.py lifespan 注册）。
清理只删除已结束的历史记录（``finished_time`` 非空），运行中的记录永不删除。
"""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.beijing import beijing_now
from app.core.logger import logger
from app.core.models.automation import AutomationRun
from app.core.settings import settings

RUN_RETENTION_DAYS = 90
RUN_RETENTION_PER_TASK = 1000
LOG_RETENTION_DAYS = 90
LOG_RETENTION_PER_TASK = 200
DAILY_CLEANUP_INTERVAL = 24 * 60 * 60

# 日志文件名约定：automation_task_{task_id}_run_{run_id}.log
_LOG_NAME_RE = re.compile(r"^automation_task_(\d+)_run_\d+\.log$")


async def cleanup_run_history(db: AsyncSession) -> int:
    """按保留策略清理运行历史，返回删除条数。"""
    cutoff = beijing_now() - timedelta(days=RUN_RETENTION_DAYS)
    deleted = 0
    result = await db.execute(
        delete(AutomationRun).where(
            AutomationRun.finished_time.is_not(None),
            AutomationRun.finished_time < cutoff,
        )
    )
    deleted += int(result.rowcount or 0)

    task_ids = (await db.scalars(select(AutomationRun.task_id).distinct())).all()
    for task_id in task_ids:
        overflow_ids = (
            await db.scalars(
                select(AutomationRun.id)
                .where(AutomationRun.task_id == task_id)
                .order_by(AutomationRun.id.desc())
                .offset(RUN_RETENTION_PER_TASK)
            )
        ).all()
        if overflow_ids:
            result = await db.execute(delete(AutomationRun).where(AutomationRun.id.in_(overflow_ids)))
            deleted += int(result.rowcount or 0)
    await db.commit()
    return deleted


def cleanup_run_logs() -> int:
    """按保留策略清理运行日志文件，返回删除文件数（目录不存在时跳过）。"""
    log_dir = Path(settings.automation_log_dir)
    if not log_dir.is_dir():
        return 0
    cutoff = beijing_now() - timedelta(days=LOG_RETENTION_DAYS)
    cutoff_ts = cutoff.timestamp()
    per_task: dict[str, list[Path]] = {}
    deleted = 0
    for path in log_dir.glob("*.log"):
        if not path.is_file():
            continue
        match = _LOG_NAME_RE.match(path.name)
        task_key = match.group(1) if match else "_other"
        try:
            if path.stat().st_mtime < cutoff_ts:
                path.unlink()
                deleted += 1
                continue
        except OSError:
            continue
        per_task.setdefault(task_key, []).append(path)
    for files in per_task.values():
        files.sort(key=lambda p: p.name, reverse=True)
        for path in files[LOG_RETENTION_PER_TASK:]:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                continue
    return deleted


async def cleanup_once(db: AsyncSession) -> tuple[int, int]:
    """执行一次完整清理，返回 ``(删除 run 数, 删除日志数)``。"""
    runs = await cleanup_run_history(db)
    logs = cleanup_run_logs()
    if runs or logs:
        logger.info("自动化任务历史清理：run %s 条，日志 %s 个", runs, logs)
    return runs, logs


async def daily_cleanup_loop(session_factory) -> None:
    """每日定时清理循环（lifespan 注册的后台任务）。"""
    while True:
        try:
            async with session_factory() as db:
                await cleanup_once(db)
        except Exception as exc:  # noqa: BLE001  清理失败不应影响主服务
            logger.warning("自动化任务定时清理失败: %s", exc)
        await asyncio.sleep(DAILY_CLEANUP_INTERVAL)
