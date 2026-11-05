"""自动化任务对 A/B 任务的引用检查（⓿-6）。

自动化任务绑定模块 A（任务调度）与模块 B（上传管理）的任务；被自动化任务绑定的
A/B 任务不允许物理/逻辑删除（含批量删除、服务器删除导致 A 任务失效的情形）。

``automation_task`` 表在阶段 ① 才创建，本模块在表不存在时直接放行（升级/未实施
阶段的行为与改造前一致）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.models import OpenListTask

_TABLE_NAMES = (
    "select name from sqlite_master where type='table' and name='automation_task'",
)


async def _automation_task_table_exists(db: AsyncSession) -> bool:
    try:
        result = await db.execute(text(_TABLE_NAMES[0]))
    except Exception:  # pragma: no cover - 兜底：读不到就按不存在处理
        return False
    return result.scalar() is not None


async def _find_referencing_automation(
    db: AsyncSession,
    *,
    openlist_task_id: Optional[int] = None,
    upload_task_id: Optional[int] = None,
) -> Optional[str]:
    """返回占用该任务的自动化任务名称；未被占用返回 None。"""
    if not await _automation_task_table_exists(db):
        return None
    conditions: list[str] = []
    params: dict[str, int] = {}
    if openlist_task_id is not None:
        conditions.append("openlist_task_id = :openlist_task_id")
        params["openlist_task_id"] = int(openlist_task_id)
    if upload_task_id is not None:
        conditions.append("upload_task_id = :upload_task_id")
        params["upload_task_id"] = int(upload_task_id)
    if not conditions:
        return None
    row = (
        await db.execute(
            text(
                "select name from automation_task "
                "where is_deleted = 0 and (" + " or ".join(conditions) + ") limit 1"
            ),
            params,
        )
    ).first()
    return str(row[0]) if row else None


async def assert_openlist_task_not_referenced(db: AsyncSession, task_id: int) -> None:
    """A 任务被自动化任务绑定时拒绝删除。"""
    name = await _find_referencing_automation(db, openlist_task_id=task_id)
    if name is not None:
        raise BadRequestException(f"任务正被自动化任务「{name}」绑定，请先解除绑定后再删除")


async def assert_upload_task_not_referenced(db: AsyncSession, task_id: int) -> None:
    """B 任务被自动化任务绑定时拒绝删除。"""
    name = await _find_referencing_automation(db, upload_task_id=task_id)
    if name is not None:
        raise BadRequestException(f"任务正被自动化任务「{name}」绑定，请先解除绑定后再删除")


async def assert_openlist_server_not_referenced(db: AsyncSession, server_id: int) -> None:
    """服务器下的 A 任务被自动化任务绑定时拒绝删除服务器。"""
    task_ids = (
        await db.scalars(
            select(OpenListTask.id).where(
                OpenListTask.server_id == server_id,
                OpenListTask.is_deleted == False,  # noqa: E712
            )
        )
    ).all()
    for task_id in task_ids:
        await assert_openlist_task_not_referenced(db, int(task_id))
