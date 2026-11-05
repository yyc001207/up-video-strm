"""上传管理路由：``/api/upload/*``（阶段一：123 云盘凭据配置）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.uploader import service
from app.business.uploader.schema import UploadPlatformConfigUpdate, UploadTestConnectionRequest
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
