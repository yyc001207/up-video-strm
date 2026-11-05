"""自动化任务：A（OpenList 调度）/ B（上传）模块的适配层（阶段③）。

引擎只依赖本层，不直接碰 A/B 的 service 内部细节：
- 创建并启动执行（冲突策略固定 skip、触发来源 automation）；
- 查询执行终态与文件统计、新上传文件名单；
- 取消执行。

A/B 的启动闸门（同任务只允许一个活跃执行）由 service 层保证：这里把
``BadRequestException("任务正在执行…")`` 原样上抛，引擎按「继续等待」处理。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business import execution_registry
from app.business.openlist import service as openlist_service
from app.business.openlist.schema import OpenListExecutionCreate
from app.business.uploader import service as uploader_service
from app.business.uploader.schema import UploadExecutionCreate
from app.core.models.openlist.execution import OpenListExecution
from app.core.models.uploader.execution import UploadExecution
from app.core.models.uploader.file_record import UploadFileRecord

#: openlist_mode -> (is_incremental, is_force, strm_only)，与 A 模块手动执行参数一致
MODE_FLAGS: dict[str, tuple[bool, bool, bool]] = {
    "incremental": (True, False, False),
    "full": (False, True, False),
    "strm_only": (True, False, True),
}

TERMINAL_STATUSES = {"success", "fail", "cancelled"}


def is_upload_active(task_id: int) -> bool:
    return execution_registry.is_task_active(execution_registry.UPLOAD, task_id)


def is_openlist_active(task_id: int) -> bool:
    return execution_registry.is_task_active(execution_registry.OPENLIST, task_id)


async def start_upload(
    db: AsyncSession,
    *,
    task_id: int,
    concurrency: int,
    retry_times: int,
    trigger_ref: str,
    trigger_name: str,
) -> int:
    """创建并启动一次 B 执行，返回执行 ID。"""
    payload = UploadExecutionCreate(
        task_id=task_id,
        conflict_policy="skip",
        concurrency=concurrency,
        retry_times=retry_times,
        dry_run=False,
    )
    execution = await uploader_service.create_execution(db, payload)
    execution_id = int(execution["id"])
    await uploader_service.start_execution(
        db,
        execution_id,
        task_id,
        trigger_source="automation",
        trigger_ref=trigger_ref,
        trigger_name=trigger_name,
    )
    return execution_id


async def start_openlist(
    db: AsyncSession,
    *,
    task_id: int,
    mode: str,
    trigger_ref: str,
    trigger_name: str,
) -> int:
    """创建并启动一次 A 执行（按 openlist_mode 映射参数），返回执行 ID。"""
    is_incremental, is_force, strm_only = MODE_FLAGS.get(mode, MODE_FLAGS["incremental"])
    payload = OpenListExecutionCreate(
        task_id=task_id,
        is_incremental=is_incremental,
        is_force=is_force,
        strm_only=strm_only,
    )
    execution = await openlist_service.create_execution(db, payload)
    execution_id = int(execution["id"])
    await openlist_service.start_execution(
        db,
        execution_id,
        task_id,
        trigger_source="automation",
        trigger_ref=trigger_ref,
        trigger_name=trigger_name,
    )
    return execution_id


async def upload_result(db: AsyncSession, execution_id: int) -> Optional[dict]:
    execution = await db.get(UploadExecution, execution_id)
    if execution is None:
        return None
    return {
        "status": execution.status,
        "error_code": execution.error_code,
        "error_message": execution.error_message,
        "file_total": execution.file_total,
        "file_success": execution.file_success,
        "file_skipped": execution.file_skipped,
        "file_failed": execution.file_failed,
        "log_path": execution.log_path,
    }


async def openlist_result(db: AsyncSession, execution_id: int) -> Optional[dict]:
    execution = await db.get(OpenListExecution, execution_id)
    if execution is None:
        return None
    return {
        "status": execution.status,
        "error_code": execution.error_code,
        "error_message": execution.error_message,
        "log_path": execution.log_path,
    }


async def uploaded_names(db: AsyncSession, execution_id: int) -> list[str]:
    """本轮 B 实际上传成功的远端文件名（用 remote_name 做可见性比对）。"""
    stmt = (
        select(UploadFileRecord.remote_name)
        .where(UploadFileRecord.execution_id == execution_id, UploadFileRecord.status == "success")
        .order_by(UploadFileRecord.id)
    )
    return [str(name) for name in (await db.scalars(stmt)).all() if name]


async def cancel_upload(db: AsyncSession, execution_id: int) -> None:
    try:
        await uploader_service.cancel_execution(db, execution_id)
    except Exception:  # pragma: no cover - 记录已被清理等情况
        pass


async def cancel_openlist(db: AsyncSession, execution_id: int) -> None:
    try:
        await openlist_service.cancel_execution(db, execution_id)
    except Exception:  # pragma: no cover
        pass
