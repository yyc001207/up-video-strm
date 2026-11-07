"""自动化任务路由：``/api/automation/*``（模块 C 配置、执行管理与运行历史）。"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.automation import execution_engine as engine
from app.business.automation import service
from app.business.automation.execution_logger import channel, recent_frames
from app.business.automation.schema import (
    AutomationBatchDeleteRequest,
    AutomationBatchStartRequest,
    AutomationCheckDirRequest,
    AutomationPendingClearRequest,
    AutomationStartRequest,
    AutomationTaskCreate,
    AutomationTaskUpdate,
)
from app.core.database import get_db
from app.core.exceptions import BadRequestException
from app.core.models.automation.task import AutomationTask
from app.utils.responses import success_response
from app.websocket.manager import ws_manager

router = APIRouter()


# ---------- 任务配置 ----------


@router.get("/tasks", summary="自动化任务列表")
async def list_tasks(
    keyword: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_tasks(db, keyword=keyword, page=page, page_size=page_size)
    return success_response(data=items, total=total)


@router.get("/tasks/{task_id}", summary="自动化任务详情")
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.get_task_detail(db, task_id))


@router.post("/tasks", summary="新建自动化任务")
async def create_task(data: AutomationTaskCreate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.create_task(db, data))


@router.put("/tasks/{task_id}", summary="编辑自动化任务")
async def update_task(task_id: int, data: AutomationTaskUpdate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.update_task(db, task_id, data))


@router.delete("/tasks/{task_id}", summary="删除自动化任务（软删除）")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.delete_task(db, task_id))


@router.post("/tasks/batch-delete", summary="批量删除自动化任务")
async def batch_delete_tasks(data: AutomationBatchDeleteRequest, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.batch_delete_tasks(db, data.ids))


@router.post("/tasks/check-dir", summary="检测校验目录映射")
async def check_dir(data: AutomationCheckDirRequest, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.check_dir(db, data))


@router.get("/bind-options", summary="可选绑定任务与推导的校验目录")
async def bind_options(
    include_task_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.bind_options(db, include_task_id=include_task_id))


# ---------- 执行管理 ----------


async def _ensure_startable(db: AsyncSession, task: AutomationTask, params: dict) -> None:
    if engine.is_running(task.id):
        raise BadRequestException("任务正在运行")
    probe = await service.check_dir(
        db,
        AutomationCheckDirRequest(
            upload_task_id=task.upload_task_id,
            check_dir=task.check_dir,
            task_id=task.id,
        ),
    )
    if not probe["reachable"]:
        raise BadRequestException(f"校验目录不可访问：{probe['error'] or '未知错误'}")
    await service.apply_run_params(db, task, params)
    await engine.start_task(task.id, force_round=True)


@router.post("/tasks/{task_id}/start", summary="启动自动化任务（强制一轮）")
async def start_task(
    task_id: int,
    data: Optional[AutomationStartRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    task = await service.get_task(db, task_id)
    params = data.model_dump(exclude_none=True) if data else {}
    await _ensure_startable(db, task, params)
    return success_response(data={"started": True, "task_id": task_id})


@router.post("/tasks/batch-start", summary="批量启动自动化任务")
async def batch_start_tasks(data: AutomationBatchStartRequest, db: AsyncSession = Depends(get_db)):
    params = data.model_dump(exclude_none=True, exclude={"task_ids"})
    results = []
    for task_id in data.task_ids:
        try:
            task = await service.get_task(db, task_id)
            await _ensure_startable(db, task, params)
            results.append({"task_id": task_id, "ok": True, "message": "已启动"})
        except Exception as exc:  # noqa: BLE001 - 逐项返回启动结果
            results.append({"task_id": task_id, "ok": False, "message": str(exc)})
    return success_response(data=results)


@router.post("/tasks/{task_id}/stop", summary="停止自动化任务")
async def stop_task(task_id: int, db: AsyncSession = Depends(get_db)):
    await service.get_task(db, task_id)
    return success_response(data=await engine.stop_task(task_id))


@router.get("/active", summary="运行中的自动化任务")
async def active_tasks(db: AsyncSession = Depends(get_db)):
    items = service.active_tasks()
    names = {}
    if items:
        rows = (
            await db.execute(
                AutomationTask.__table__.select().where(
                    AutomationTask.__table__.c.id.in_([item["task_id"] for item in items])
                )
            )
        ).all()
        names = {row.id: row.name for row in rows}
    return success_response(data=[{**item, "task_name": names.get(item["task_id"])} for item in items])


@router.post("/tasks/{task_id}/reset-fingerprint", summary="重置本地扫描指纹")
async def reset_fingerprint(task_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.reset_fingerprint(db, task_id))


@router.post("/tasks/{task_id}/pending/clear", summary="清空待校验文件")
async def clear_pending(
    task_id: int,
    data: Optional[AutomationPendingClearRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    remote_names = data.remote_names if data else None
    return success_response(data=await service.clear_pending(db, task_id, remote_names))


# ---------- 运行历史 ----------


@router.get("/runs", summary="运行历史列表")
async def list_runs(
    task_id: Optional[int] = None,
    status: Optional[str] = None,
    start_time: Optional[date] = None,
    end_time: Optional[date] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_runs(
        db,
        task_id=task_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )
    return success_response(data=items, total=total)


@router.get("/runs/{run_id}", summary="运行详情")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.get_run_detail(db, run_id))


@router.get("/runs/{run_id}/logs", summary="运行日志")
async def get_run_logs(
    run_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=2000),
):
    return success_response(data=service.read_run_logs(run_id, offset=offset, limit=limit))


@router.post("/runs/{run_id}/retry-failed", summary="重试失败文件（写回 pending，不自动启动）")
async def retry_failed(run_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.retry_failed(db, run_id))


# ---------- 实时日志（WebSocket） ----------


def _replay_frames(frames: list[dict]) -> list[dict]:
    """给回放帧统一加 ``replay=True``：前端据此丢弃，避免把上一轮的终态/日志当成本轮实时状态。"""
    return [{**frame, "replay": True} for frame in frames]


@router.websocket("/ws/{task_id}")
async def task_ws(websocket: WebSocket, task_id: int):
    key = channel(task_id)
    await ws_manager.connect(key, websocket)
    await ws_manager.send_recent(key, websocket, _replay_frames(recent_frames(task_id)))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(key, websocket)
