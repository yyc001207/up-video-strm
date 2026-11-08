"""本地改名路由：``/api/renamer/*``（目录扫描、批量重命名与操作日志）。"""

from fastapi import APIRouter, Query

from app.business.renamer import service
from app.business.renamer.schema import RenameRequest, RenameScanRequest
from app.core.exceptions import BadRequestException
from app.utils.responses import success_response

router = APIRouter()


@router.post("/scan", summary="扫描文件夹并识别剧集结构")
async def scan(data: RenameScanRequest):
    try:
        plan = await service.scan_async(data.path)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    return success_response(data=plan)


@router.post("/rename", summary="批量重命名扫描结果中的文件")
async def rename(data: RenameRequest):
    entries = [entry.model_dump() for entry in data.entries]
    try:
        results = await service.rename_async(data.root, entries, data.conflict_mode, data.keep_lang)
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc
    return success_response(data={"results": results})


@router.get("/logs", summary="最近的操作日志（最新在前）")
async def logs(limit: int = Query(default=200, ge=1, le=1000)):
    return success_response(data={"logs": service.recent_logs(limit)})
