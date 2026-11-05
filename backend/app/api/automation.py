"""自动化任务路由：``/api/automation/*``（模块 C 任务配置）。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.automation import service
from app.business.automation.schema import (
    AutomationBatchDeleteRequest,
    AutomationCheckDirRequest,
    AutomationTaskCreate,
    AutomationTaskUpdate,
)
from app.core.database import get_db
from app.utils.responses import success_response

router = APIRouter()


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
