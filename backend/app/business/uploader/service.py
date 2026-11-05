"""上传管理业务逻辑：123 云盘凭据、重命名规则与上传任务。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.uploader import rename_engine
from app.business.uploader.rename_engine import DEFAULT_TEMPLATE
from app.business.uploader.pan123_client import Pan123Client
from app.business.uploader.schema import (
    UploadPlatformConfigUpdate,
    UploadRenamePreviewRequest,
    UploadRenameRuleCreate,
    UploadRenameRuleUpdate,
    UploadTaskCreate,
    UploadTaskUpdate,
    UploadTestConnectionRequest,
)
from app.core.exceptions import BadRequestException
from app.core.models.uploader import UploadPlatformConfig, UploadRenameRule, UploadTask
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


# ---------------------------------------------------------------------------
# 重命名规则
# ---------------------------------------------------------------------------


def _rule_to_dict(rule: UploadRenameRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "template": rule.template,
        "created_time": rule.created_time,
        "updated_time": rule.updated_time,
    }


async def seed_default_rename_rule(db: AsyncSession) -> None:
    """初始化时保证至少存在一条默认重命名规则。"""
    exists = await db.scalar(select(UploadRenameRule.id).limit(1))
    if exists is not None:
        return
    db.add(UploadRenameRule(name="默认 SxxExx", template=DEFAULT_TEMPLATE))
    await db.commit()


async def list_rename_rules(db: AsyncSession) -> list[dict]:
    rules = (await db.scalars(select(UploadRenameRule).order_by(UploadRenameRule.id))).all()
    return [_rule_to_dict(rule) for rule in rules]


async def _get_rule(db: AsyncSession, rule_id: int) -> UploadRenameRule:
    rule = await db.get(UploadRenameRule, rule_id)
    if rule is None:
        raise BadRequestException("重命名规则不存在")
    return rule


async def create_rename_rule(db: AsyncSession, data: UploadRenameRuleCreate) -> dict:
    try:
        template = rename_engine.validate_template(data.template or DEFAULT_TEMPLATE)
    except rename_engine.RenameError as exc:
        raise BadRequestException(str(exc)) from exc
    rule = UploadRenameRule(name=data.name.strip(), template=template)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


async def update_rename_rule(db: AsyncSession, rule_id: int, data: UploadRenameRuleUpdate) -> dict:
    rule = await _get_rule(db, rule_id)
    if data.name is not None:
        rule.name = data.name.strip()
    if data.template is not None:
        try:
            rule.template = rename_engine.validate_template(data.template)
        except rename_engine.RenameError as exc:
            raise BadRequestException(str(exc)) from exc
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


async def delete_rename_rule(db: AsyncSession, rule_id: int) -> dict:
    rule = await _get_rule(db, rule_id)
    used = await db.scalar(select(UploadTask.id).where(UploadTask.rename_rule_id == rule_id).limit(1))
    if used is not None:
        raise BadRequestException("该规则正被上传任务使用，无法删除")
    await db.delete(rule)
    await db.commit()
    return {"id": rule_id}


async def _resolve_template(db: AsyncSession, rename_rule_id: Optional[int], template: Optional[str]) -> str:
    """预览/执行时确定模板：显式模板 > 规则模板 > 默认模板。"""
    if template:
        try:
            return rename_engine.validate_template(template)
        except rename_engine.RenameError as exc:
            raise BadRequestException(str(exc)) from exc
    if rename_rule_id is not None:
        return (await _get_rule(db, rename_rule_id)).template
    return DEFAULT_TEMPLATE


async def preview_rename(db: AsyncSession, data: UploadRenamePreviewRequest) -> dict:
    """按任务参数预览单个文件的重命名结果（不落库）。"""
    template = await _resolve_template(db, data.rename_rule_id, data.template)
    try:
        plan = rename_engine.plan_rename(
            data.filename,
            season=data.season,
            start_episode=data.start_episode,
            template=template,
        )
    except rename_engine.RenameError as exc:
        return {"matched": False, "message": str(exc), "source_name": data.filename}
    return {
        "matched": True,
        "message": "匹配成功",
        "source_name": plan.source_name,
        "output_name": plan.output_name,
        "absolute_episode": plan.absolute_episode,
        "season": plan.season,
        "episode": plan.episode,
    }


# ---------------------------------------------------------------------------
# 上传任务
# ---------------------------------------------------------------------------


def _task_to_dict(task: UploadTask, rule_name: Optional[str] = None) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "local_dir": task.local_dir,
        "remote_dir": task.remote_dir,
        "season": task.season,
        "start_episode": task.start_episode,
        "rename_rule_id": task.rename_rule_id,
        "rename_rule_name": rule_name,
        "created_time": task.created_time,
        "updated_time": task.updated_time,
    }


def _validate_local_dir(local_dir: str) -> str:
    path = Path(local_dir.strip()).expanduser()
    if not path.is_dir():
        raise BadRequestException(f"本地目录不存在或不是文件夹：{path}")
    return str(path)


def _normalize_remote_dir(remote_dir: str) -> str:
    """目标目录必须是绝对路径（以 / 开头），且不能是根目录。"""
    value = (remote_dir or "").strip()
    if not value.startswith("/"):
        value = "/" + value
    value = "/" + value.strip("/")
    if value in ("", "/"):
        raise BadRequestException("123 云盘目标目录不能是根目录")
    return value


async def _validate_rule(db: AsyncSession, rule_id: Optional[int]) -> None:
    if rule_id is None:
        return
    await _get_rule(db, rule_id)


async def list_upload_tasks(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(UploadTask, UploadRenameRule.name)
            .outerjoin(UploadRenameRule, UploadRenameRule.id == UploadTask.rename_rule_id)
            .order_by(UploadTask.id)
        )
    ).all()
    return [_task_to_dict(task, rule_name) for task, rule_name in rows]


async def get_upload_task(db: AsyncSession, task_id: int) -> dict:
    task = await db.get(UploadTask, task_id)
    if task is None:
        raise BadRequestException("上传任务不存在")
    rule_name = None
    if task.rename_rule_id is not None:
        rule = await db.get(UploadRenameRule, task.rename_rule_id)
        rule_name = rule.name if rule else None
    return _task_to_dict(task, rule_name)


async def create_upload_task(db: AsyncSession, data: UploadTaskCreate) -> dict:
    await _validate_rule(db, data.rename_rule_id)
    task = UploadTask(
        name=data.name.strip(),
        local_dir=_validate_local_dir(data.local_dir),
        remote_dir=_normalize_remote_dir(data.remote_dir),
        season=data.season,
        start_episode=data.start_episode,
        rename_rule_id=data.rename_rule_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return await get_upload_task(db, task.id)


async def update_upload_task(db: AsyncSession, task_id: int, data: UploadTaskUpdate) -> dict:
    task = await db.get(UploadTask, task_id)
    if task is None:
        raise BadRequestException("上传任务不存在")
    if data.rename_rule_id is not None:
        await _validate_rule(db, data.rename_rule_id)
        task.rename_rule_id = data.rename_rule_id
    if data.name is not None:
        task.name = data.name.strip()
    if data.local_dir is not None:
        task.local_dir = _validate_local_dir(data.local_dir)
    if data.remote_dir is not None:
        task.remote_dir = _normalize_remote_dir(data.remote_dir)
    if data.season is not None:
        task.season = data.season
    if data.start_episode is not None:
        task.start_episode = data.start_episode
    await db.commit()
    await db.refresh(task)
    return await get_upload_task(db, task_id)


async def delete_upload_task(db: AsyncSession, task_id: int) -> dict:
    task = await db.get(UploadTask, task_id)
    if task is None:
        raise BadRequestException("上传任务不存在")
    await db.delete(task)
    await db.commit()
    return {"id": task_id}


# ---------------------------------------------------------------------------
# 123 云盘目录浏览（任务配置选择目标目录用）
# ---------------------------------------------------------------------------


async def list_remote_dirs(db: AsyncSession, parent_id: int = 0, path: str = "/") -> dict:
    """列出 123 云盘某个目录下的子目录（不自动创建，缺失时由调用方提示）。"""
    token = await get_access_token(db)
    async with await build_client(db) as client:
        files = await client.list_all_files(token, parent_file_id=parent_id)
    items = [
        {
            "file_id": int(item.get("fileId") or 0),
            "file_name": str(item.get("filename") or ""),
            "type": int(item.get("type") or 0),
            "is_dir": int(item.get("type") or 0) == 1,
        }
        for item in files
        if int(item.get("type") or 0) == 1
    ]
    items.sort(key=lambda item: item["file_name"].lower())
    return {"parent_id": parent_id, "path": path, "items": items}
