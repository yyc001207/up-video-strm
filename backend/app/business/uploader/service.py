"""上传管理业务逻辑（阶段一：123 云盘凭据、Token 缓存与连通性测试）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.uploader.pan123_client import Pan123Client
from app.business.uploader.schema import UploadPlatformConfigUpdate, UploadTestConnectionRequest
from app.core.exceptions import BadRequestException
from app.core.models.uploader import UploadPlatformConfig
from app.core.secret_store import decrypt_secret, encrypt_secret, mask_secret

# 提前 5 分钟判定过期，避免上传途中 token 失效
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)

TOKEN_STATUS_NONE = "none"
TOKEN_STATUS_VALID = "valid"
TOKEN_STATUS_EXPIRED = "expired"


async def _load_config(db: AsyncSession) -> UploadPlatformConfig:
    """读取唯一一行凭据配置，不存在时自动创建空行。"""
    config = await db.scalar(select(UploadPlatformConfig).order_by(UploadPlatformConfig.id).limit(1))
    if config is None:
        config = UploadPlatformConfig()
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


def _token_status(config: UploadPlatformConfig) -> str:
    if not config.access_token:
        return TOKEN_STATUS_NONE
    if config.token_expires_at is None:
        return TOKEN_STATUS_VALID
    if config.token_expires_at <= datetime.now() + TOKEN_REFRESH_MARGIN:
        return TOKEN_STATUS_EXPIRED
    return TOKEN_STATUS_VALID


async def get_config(db: AsyncSession) -> dict:
    """读取凭据配置：密钥只回显脱敏值，不返回明文。"""
    config = await _load_config(db)
    secret = decrypt_secret(config.client_secret)
    return {
        "client_id": config.client_id or "",
        "has_secret": bool(secret),
        "secret_masked": mask_secret(secret),
        "token_status": _token_status(config),
        "token_expires_at": config.token_expires_at,
        "updated_time": config.updated_time,
    }


async def update_config(db: AsyncSession, data: UploadPlatformConfigUpdate) -> dict:
    """保存凭据；clientSecret 留空表示保持不变。凭据变化后清空缓存的 Token。"""
    config = await _load_config(db)
    if data.client_id is not None:
        config.client_id = data.client_id.strip() or None
        config.access_token = None
        config.token_expires_at = None
    if data.client_secret is not None and data.client_secret.strip():
        config.client_secret = encrypt_secret(data.client_secret.strip())
        config.access_token = None
        config.token_expires_at = None
    await db.commit()
    await db.refresh(config)
    return await get_config(db)


async def _resolve_credentials(
    db: AsyncSession,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> tuple[str, str]:
    """取凭据：优先使用本次传入值（测试连接场景），否则回退到已保存值。"""
    config = await _load_config(db)
    resolved_id = (client_id or "").strip() or (config.client_id or "")
    resolved_secret = (client_secret or "").strip() or decrypt_secret(config.client_secret)
    if not resolved_id:
        raise BadRequestException("未配置 123 云盘 clientID，请先在全局配置中填写")
    if not resolved_secret:
        raise BadRequestException("未配置 123 云盘 clientSecret，请先在全局配置中填写")
    return resolved_id, resolved_secret


async def test_connection(db: AsyncSession, data: UploadTestConnectionRequest) -> dict:
    """用当前凭据换 token 并读取根目录，验证凭据与网络。"""
    client_id, client_secret = await _resolve_credentials(db, data.client_id, data.client_secret)
    async with Pan123Client(client_id, client_secret) as client:
        message = await client.test_connection()
    return {"message": message}


async def get_access_token(db: AsyncSession, *, force_refresh: bool = False) -> str:
    """获取可用 access_token（带缓存与提前刷新）。"""
    config = await _load_config(db)
    if not force_refresh and config.access_token and _token_status(config) == TOKEN_STATUS_VALID:
        return decrypt_secret(config.access_token)
    client_id, client_secret = await _resolve_credentials(db)
    async with Pan123Client(client_id, client_secret) as client:
        token, expires_at = await client.get_access_token()
    config.access_token = encrypt_secret(token)
    config.token_expires_at = expires_at
    await db.commit()
    await db.refresh(config)
    return token


async def build_client(db: AsyncSession) -> Pan123Client:
    """构建已配置凭据的客户端（调用方负责 ``async with`` / ``aclose``）。"""
    client_id, client_secret = await _resolve_credentials(db)
    return Pan123Client(client_id, client_secret)
