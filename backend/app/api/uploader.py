"""上传管理路由：``/api/upload/*``（123 云盘凭据、重命名规则、上传任务、执行与实时日志）。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.uploader import service
from app.business.uploader.schema import (
    UploadBatchDeleteRequest,
    UploadExecutionBatchCreate,
    UploadExecutionCancel,
    UploadExecutionCreate,
    UploadExecutionStart,
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
from app.websocket.manager import ws_manager

router = APIRouter()


@router.get("/config", summary="123 云盘凭据配置")
async def get_platform_config(db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.get_config(db))


@router.put("/config", summary="保存 123 云盘凭据")
async def update_platform_config(data: UploadPlatformConfigUpdate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.update_config(db, data))


@router.delete("/config", summary="清空 123 云盘凭据")
async def clear_platform_config(db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.clear_config(db))


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


@router.post("/rules/batch-delete", summary="批量删除重命名规则")
async def batch_delete_rename_rules(data: UploadBatchDeleteRequest, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.batch_delete_rename_rules(db, data.ids))


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


@router.post("/tasks/batch-delete", summary="批量删除上传任务")
async def batch_delete_upload_tasks(data: UploadBatchDeleteRequest, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.batch_delete_upload_tasks(db, data.ids))


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


# ---------------------------------------------------------------------------
# 执行记录（创建 → 启动 → 取消 → 列表/详情/文件明细/日志）
# ---------------------------------------------------------------------------


@router.post("/executions", summary="创建上传执行记录（不启动）")
async def create_execution(data: UploadExecutionCreate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.create_execution(db, data))


@router.post("/executions/batch", summary="批量创建上传执行记录")
async def batch_create_executions(data: UploadExecutionBatchCreate, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.batch_create_executions(db, data))


@router.post("/executions/start", summary="启动执行（连上 WS 后调用）")
async def start_execution(data: UploadExecutionStart, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.start_execution(db, data.execution_id, data.task_id))


@router.post("/executions/cancel", summary="取消执行")
async def cancel_execution(data: UploadExecutionCancel, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.cancel_execution(db, data.execution_id))


@router.get("/executions", summary="执行记录列表")
async def list_executions(
    task_id: Optional[int] = Query(default=None, description="按任务筛选"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_executions(db, task_id, status, page, pageSize)
    return success_response(data={"list": items}, total=total)


@router.get("/executions/{execution_id}", summary="执行详情（含文件明细前 500 条）")
async def get_execution_detail(execution_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.get_execution_detail(db, execution_id))


@router.get("/executions/{execution_id}/records", summary="执行文件明细（分页）")
async def list_file_records(
    execution_id: int,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_file_records(db, execution_id, page, pageSize)
    return success_response(data={"list": items}, total=total)


@router.get("/executions/{execution_id}/logs", summary="执行日志（分页）")
async def list_execution_logs(
    execution_id: int,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.list_execution_logs(db, execution_id, page, pageSize)
    return success_response(data={"list": items}, total=total)


@router.get("/history", summary="历史汇总（按任务：最近执行 + 执行次数）")
async def history_summary(db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.history_summary(db))


@router.get("/history/task/{task_id}", summary="某任务的全部执行记录（分页）")
async def history_by_task(
    task_id: int,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await service.history_by_task(db, task_id, page, pageSize)
    return success_response(data={"list": items}, total=total)


@router.post("/executions/{execution_id}/retry", summary="以原参数重跑（新建执行记录，不启动）")
async def retry_execution(execution_id: int, db: AsyncSession = Depends(get_db)):
    return success_response(data=await service.retry_execution(db, execution_id))


# ---------------------------------------------------------------------------
# 实时日志（WebSocket）
# ---------------------------------------------------------------------------


@router.websocket("/ws/{execution_id}")
async def execution_ws(websocket: WebSocket, execution_id: int):
    # 本地部署无鉴权：直接接受连接
    await ws_manager.connect(execution_id, websocket)
    recent = await service.get_recent_log_lines(execution_id, limit=200)
    await ws_manager.send_recent(execution_id, websocket, recent)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(execution_id, websocket)
