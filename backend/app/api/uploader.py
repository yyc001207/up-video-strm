"""上传管理路由：``/api/upload/*``（123 云盘凭据、重命名规则、上传任务）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.uploader import service
from app.business.uploader.schema import (
    UploadPlatformConfigUpdate,
    UploadRenamePreviewRequest,
    UploadRenameRuleCreate,
    UploadRenameRuleUpdate,
    UploadTaskCreate,
    UploadTaskUpdate,
    UploadTestConnectionRequest,
)
from app.core.database import get_db
from app.utils.responses import success_response

router = APIRouter()


@router.get("/config", summary="123 云盘凭据配置")
async def get_platform_config(db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.get_config(db))


@router.put("/config", summary="保存 123 云盘凭据")
async def update_platform_config(data: UploadPlatformConfigUpdate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.update_config(db, data))


@router.post("/config/test-connection", summary="测试 123 云盘凭据连通性")
async def test_platform_connection(data: UploadTestConnectionRequest, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.test_connection(db, data))


# ---------------------------------------------------------------------------
# 重命名规则
# ---------------------------------------------------------------------------


@router.get("/rules", summary="重命名规则列表")
async def list_rename_rules(db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.list_rename_rules(db))


@router.post("/rules", summary="新增重命名规则")
async def create_rename_rule(data: UploadRenameRuleCreate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.create_rename_rule(db, data))


@router.post("/rules/preview", summary="预览重命名结果")
async def preview_rename(data: UploadRenamePreviewRequest, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.preview_rename(db, data))


@router.put("/rules/{rule_id}", summary="修改重命名规则")
async def update_rename_rule(rule_id: int, data: UploadRenameRuleUpdate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.update_rename_rule(db, rule_id, data))


@router.delete("/rules/{rule_id}", summary="删除重命名规则")
async def delete_rename_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.delete_rename_rule(db, rule_id))


# ---------------------------------------------------------------------------
# 上传任务
# ---------------------------------------------------------------------------


@router.get("/tasks", summary="上传任务列表")
async def list_upload_tasks(db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.list_upload_tasks(db))


@router.post("/tasks", summary="新增上传任务")
async def create_upload_task(data: UploadTaskCreate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.create_upload_task(db, data))


@router.get("/tasks/{task_id}", summary="上传任务详情")
async def get_upload_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.get_upload_task(db, task_id))


@router.put("/tasks/{task_id}", summary="修改上传任务")
async def update_upload_task(task_id: int, data: UploadTaskUpdate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.update_upload_task(db, task_id, data))


@router.delete("/tasks/{task_id}", summary="删除上传任务")
async def delete_upload_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.delete_upload_task(db, task_id))


@router.get("/remote/dirs", summary="浏览 123 云盘目录")
async def list_remote_dirs(
    parent_id: int = 0,
    path: str = "/",
    db: AsyncSession = Depends(get_db),
):
    return success_response(data=await service.list_remote_dirs(db, parent_id, path))
