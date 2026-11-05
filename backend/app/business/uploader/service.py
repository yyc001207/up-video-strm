"""上传管理业务逻辑：123 云盘凭据、重命名规则与上传任务。"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.beijing import beijing_now
from app.business.uploader import rename_engine
from app.business.uploader.rename_engine import DEFAULT_TEMPLATE
from app.business.uploader.pan123_client import Pan123Client, get_file_id
from app.business.uploader.schema import (
    UploadExecutionBatchCreate,
    UploadExecutionCreate,
    UploadPlatformConfigUpdate,
    UploadRenamePreviewRequest,
    UploadRenameRuleCreate,
    UploadRenameRuleUpdate,
    UploadTaskCreate,
    UploadTaskUpdate,
    UploadTestConnectionRequest,
)
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.models.uploader import (
    UploadExecution,
    UploadFileRecord,
    UploadPlatformConfig,
    UploadRenameRule,
    UploadTask,
)
from app.core.secret_store import decrypt_secret, encrypt_secret, mask_secret
from app.core.settings import settings

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
    if config.token_expires_at <= beijing_now() + TOKEN_REFRESH_MARGIN:
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
            "file_id": get_file_id(item),
            "file_name": str(item.get("filename") or ""),
            "type": int(item.get("type") or 0),
            "is_dir": int(item.get("type") or 0) == 1,
        }
        for item in files
        if int(item.get("type") or 0) == 1
    ]
    items.sort(key=lambda item: item["file_name"].lower())
    return {"parent_id": parent_id, "path": path, "items": items}


# ---------------------------------------------------------------------------
# 执行记录（单任务 / 批量创建 → 连 WS 后启动 → 取消 → 列表/详情）
# ---------------------------------------------------------------------------


def execution_to_dict(execution: UploadExecution) -> dict:
    return {
        "id": execution.id,
        "task_id": execution.task_id,
        "task_name": execution.task_name,
        "local_dir": execution.local_dir,
        "remote_dir": execution.remote_dir,
        "season": execution.season,
        "start_episode": execution.start_episode,
        "rename_rule_id": execution.rename_rule_id,
        "template": execution.template,
        "conflict_policy": execution.conflict_policy,
        "concurrency": execution.concurrency,
        "retry_times": execution.retry_times,
        "dry_run": execution.dry_run,
        "status": execution.status,
        "file_total": execution.file_total,
        "file_success": execution.file_success,
        "file_skipped": execution.file_skipped,
        "file_failed": execution.file_failed,
        "bytes_uploaded": execution.bytes_uploaded,
        "duration_seconds": execution.duration_seconds,
        "log_path": execution.log_path,
        "started_time": execution.started_time,
        "finished_time": execution.finished_time,
        "created_time": execution.created_time,
    }


def _record_to_dict(record: UploadFileRecord) -> dict:
    return {
        "id": record.id,
        "execution_id": record.execution_id,
        "local_path": record.local_path,
        "remote_name": record.remote_name,
        "size": record.size,
        "md5": record.md5,
        "status": record.status,
        "phase": record.phase,
        "reason": record.reason,
        "remote_file_id": record.remote_file_id,
        "replaced_file_id": record.replaced_file_id,
        "created_time": record.created_time,
        "updated_time": record.updated_time,
    }


async def _get_execution(db: AsyncSession, execution_id: int) -> UploadExecution:
    execution = await db.get(UploadExecution, execution_id)
    if execution is None or execution.is_deleted:
        raise NotFoundException("执行记录不存在")
    return execution


async def _resolve_task_template(db: AsyncSession, task: UploadTask) -> str:
    """执行创建时固化命名模板：规则模板 > 默认模板。"""
    if task.rename_rule_id is not None:
        rule = await db.get(UploadRenameRule, task.rename_rule_id)
        if rule is not None:
            return rule.template
    return DEFAULT_TEMPLATE


async def _create_execution_row(db: AsyncSession, data: UploadExecutionCreate) -> UploadExecution:
    task = await db.get(UploadTask, data.task_id)
    if task is None:
        raise BadRequestException("上传任务不存在")
    execution = UploadExecution(
        task_id=task.id,
        task_name=task.name,
        local_dir=task.local_dir,
        remote_dir=task.remote_dir,
        season=task.season,
        start_episode=task.start_episode,
        rename_rule_id=task.rename_rule_id,
        template=await _resolve_task_template(db, task),
        conflict_policy=data.conflict_policy,
        concurrency=data.concurrency,
        retry_times=data.retry_times,
        dry_run=data.dry_run,
        status="running",
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def create_execution(db: AsyncSession, data: UploadExecutionCreate) -> dict:
    """创建执行记录（仅落库，不启动）。"""
    execution = await _create_execution_row(db, data)
    return execution_to_dict(execution)


async def batch_create_executions(db: AsyncSession, data: UploadExecutionBatchCreate) -> list[dict]:
    """批量创建执行记录（多任务共享执行参数）。"""
    results: list[dict] = []
    task_ids = list(dict.fromkeys(data.task_ids))
    for task_id in task_ids:
        execution = await _create_execution_row(
            db,
            UploadExecutionCreate(
                task_id=task_id,
                conflict_policy=data.conflict_policy,
                concurrency=data.concurrency,
                retry_times=data.retry_times,
                dry_run=data.dry_run,
            ),
        )
        results.append(execution_to_dict(execution))
    return results


async def start_execution(db: AsyncSession, execution_id: int, task_id: int) -> dict:
    """启动已创建的执行记录：置 started_time 后拉起后台流水线。

    只有 ``running`` 且尚未启动过的记录才能启动，防止重复点击重复启动。
    """
    execution = await _get_execution(db, execution_id)
    if execution.task_id != task_id:
        raise BadRequestException("执行记录与任务不匹配")
    if execution.status != "running":
        raise BadRequestException("执行记录不可启动，当前状态: " + execution.status)
    if execution.started_time is not None:
        raise BadRequestException("执行记录已启动")

    execution.started_time = beijing_now()
    await db.commit()
    await db.refresh(execution)

    # 延迟导入，避免 service ↔ execution_engine 循环引用
    from app.business.uploader.execution_engine import run_upload

    asyncio.create_task(run_upload(execution_id=execution.id))
    return execution_to_dict(execution)


async def cancel_execution(db: AsyncSession, execution_id: int) -> dict:
    execution = await _get_execution(db, execution_id)
    if execution.status != "running":
        return {"cancelled": False, "status": execution.status}
    from app.business.openlist.task_status_manager import TaskStatusManager

    TaskStatusManager.cancel(str(execution.id))
    execution.status = "cancelled"
    execution.finished_time = beijing_now()
    await db.commit()
    return {"cancelled": True, "status": "cancelled"}


async def list_executions(
    db: AsyncSession,
    task_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    stmt = select(UploadExecution).where(UploadExecution.is_deleted == False)  # noqa: E712
    if task_id is not None:
        stmt = stmt.where(UploadExecution.task_id == task_id)
    if status:
        stmt = stmt.where(UploadExecution.status == status)
    total = await db.scalar(select(func.count(UploadExecution.id)).where(stmt.whereclause)) or 0
    result = await db.execute(
        stmt.order_by(UploadExecution.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return [execution_to_dict(item) for item in result.scalars()], total


async def get_execution_detail(db: AsyncSession, execution_id: int) -> dict:
    execution = await _get_execution(db, execution_id)
    result = await db.execute(
        select(UploadFileRecord)
        .where(UploadFileRecord.execution_id == execution_id)
        .order_by(UploadFileRecord.id)
        .limit(500)
    )
    return {
        "execution": execution_to_dict(execution),
        "records": [_record_to_dict(record) for record in result.scalars()],
    }


async def list_file_records(
    db: AsyncSession, execution_id: int, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    await _get_execution(db, execution_id)
    total = (
        await db.scalar(
            select(func.count(UploadFileRecord.id)).where(UploadFileRecord.execution_id == execution_id)
        )
        or 0
    )
    result = await db.execute(
        select(UploadFileRecord)
        .where(UploadFileRecord.execution_id == execution_id)
        .order_by(UploadFileRecord.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [_record_to_dict(item) for item in result.scalars()], total


# ---------------------------------------------------------------------------
# 历史汇总 / 按任务历史 / 失败重跑（阶段四）
# ---------------------------------------------------------------------------


async def history_summary(db: AsyncSession) -> list[dict]:
    """按任务汇总历史：任务信息 + 最近一次执行 + 执行次数。"""
    tasks_result = await db.execute(select(UploadTask).order_by(UploadTask.id.desc()))
    tasks = list(tasks_result.scalars())
    if not tasks:
        return []

    last_id_rows = await db.execute(
        select(func.max(UploadExecution.id))
        .where(UploadExecution.is_deleted == False)  # noqa: E712
        .group_by(UploadExecution.task_id)
    )
    last_ids = [row[0] for row in last_id_rows if row[0] is not None]
    latest: dict[int, dict] = {}
    if last_ids:
        latest_result = await db.execute(select(UploadExecution).where(UploadExecution.id.in_(last_ids)))
        for execution in latest_result.scalars():
            latest[execution.task_id] = execution_to_dict(execution)

    count_rows = await db.execute(
        select(UploadExecution.task_id, func.count(UploadExecution.id))
        .where(UploadExecution.is_deleted == False)  # noqa: E712
        .group_by(UploadExecution.task_id)
    )
    counts = {task_id: total for task_id, total in count_rows}

    return [
        {
            "task_id": task.id,
            "task_name": task.name,
            "local_dir": task.local_dir,
            "remote_dir": task.remote_dir,
            "season": task.season,
            "start_episode": task.start_episode,
            "total_executions": counts.get(task.id, 0),
            "last_execution": latest.get(task.id),
        }
        for task in tasks
    ]


async def history_by_task(
    db: AsyncSession, task_id: int, page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    """某任务的全部执行记录（分页，倒序）。"""
    await get_upload_task(db, task_id)
    return await list_executions(db, task_id=task_id, page=page, page_size=page_size)


async def retry_execution(db: AsyncSession, execution_id: int) -> dict:
    """以原执行固化的参数重新创建一条执行记录（整任务重跑，不启动）。"""
    execution = await _get_execution(db, execution_id)
    task = await db.get(UploadTask, execution.task_id)
    if task is None:
        raise NotFoundException("原任务已被删除，无法重跑")

    new_execution = UploadExecution(
        task_id=execution.task_id,
        task_name=execution.task_name,
        local_dir=execution.local_dir,
        remote_dir=execution.remote_dir,
        season=execution.season,
        start_episode=execution.start_episode,
        rename_rule_id=execution.rename_rule_id,
        template=execution.template,
        conflict_policy=execution.conflict_policy,
        concurrency=execution.concurrency,
        retry_times=execution.retry_times,
        dry_run=False,
        status="running",
    )
    db.add(new_execution)
    await db.commit()
    await db.refresh(new_execution)
    return execution_to_dict(new_execution)


# ---------------------------------------------------------------------------
# 执行日志文件读取（与 OpenList 模块同构，文件为唯一权威源）
# ---------------------------------------------------------------------------

_LOG_LINE_RE = re.compile(r"^\[([^\]]*)\] \[([A-Z]+)\] (.*)$", re.DOTALL)


def _log_path(execution_id: int) -> Path:
    return Path(settings.upload_log_dir) / f"execution_{execution_id}.log"


def _read_log_file(execution_id: int, offset: int = 0, limit: int = 200) -> Optional[list[dict]]:
    path = _log_path(execution_id)
    try:
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        return None
    items = []
    for line in lines[offset : offset + limit]:
        match = _LOG_LINE_RE.match(line)
        if not match:
            continue
        ts, level, message = match.group(1), match.group(2).lower(), match.group(3)
        items.append({"log_level": level, "content": message, "created_time": ts or None})
    return items


def _log_file_total(execution_id: int) -> Optional[int]:
    path = _log_path(execution_id)
    try:
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return None


async def list_execution_logs(
    db: AsyncSession, execution_id: int, page: int = 1, page_size: int = 200
) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    file_logs = _read_log_file(execution_id, offset, page_size)
    if file_logs is not None:
        total = _log_file_total(execution_id) or 0
        return [{"id": offset + i + 1, **item} for i, item in enumerate(file_logs)], total
    return [], 0


async def get_recent_log_lines(execution_id: int, limit: int = 200) -> list[dict]:
    """WebSocket 重连时回放最近的日志帧（读日志文件末尾）。"""
    path = _log_path(execution_id)
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            frames = []
            for line in lines[-limit:]:
                match = _LOG_LINE_RE.match(line)
                if not match:
                    continue
                ts, level, message = match.group(1), match.group(2).lower(), match.group(3)
                frames.append({"type": "log", "level": level, "message": message, "ts": ts or None})
            return frames
    except Exception:
        pass
    return []
