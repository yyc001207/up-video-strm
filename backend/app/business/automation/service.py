"""自动化任务（模块 C）业务服务：任务 CRUD、绑定选项、校验目录检测。

本模块只处理「配置」层；链式执行状态机在 ``execution_engine.py``（阶段③）。
校验目录（``check_dir``）是模块 B ``remote_dir`` 经全局 ``openlist_remote_prefix``
规范化后的**精确映射**，保存时强校验一致性，目录不可达只警告不阻止保存。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.automation import registry
from app.business.automation.schema import (
    AutomationCheckDirRequest,
    AutomationTaskCreate,
    AutomationTaskUpdate,
)
from app.business.openlist.openlist_api import OpenListAPI
from app.business.openlist.service import get_active_server
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.models.automation import AutomationRun, AutomationTask
from app.core.models.openlist.config import OpenListConfig
from app.core.models.openlist.execution import OpenListExecution
from app.core.models.openlist.task import OpenListTask
from app.core.models.uploader import UploadTask
from app.core.models.uploader.execution import UploadExecution
from app.core.settings import settings

_OPENLIST_MODES = {"incremental", "full", "strm_only"}
_MAX_SAMPLE_FILES = 20


# ---------------------------------------------------------------------------
# 路径与配置辅助
# ---------------------------------------------------------------------------


def normalize_dir(path: Optional[str]) -> str:
    """目录规范化：统一分隔符、合并重复斜杠、保证以 ``/`` 开头且不以 ``/`` 结尾。"""
    text = (path or "").strip().replace("\\", "/")
    if not text:
        return ""
    text = re.sub(r"/+", "/", text)
    if not text.startswith("/"):
        text = "/" + text
    if len(text) > 1:
        text = text.rstrip("/") or "/"
    return text


def expected_check_dir(remote_dir: str, remote_prefix: str = "") -> str:
    """由 B ``remote_dir`` 与全局前缀推导 C 的校验目录。"""
    return normalize_dir(f"{remote_prefix}/{remote_dir}")


async def _load_remote_prefix(db: AsyncSession) -> str:
    config = await db.scalar(select(OpenListConfig).limit(1))
    return (config.openlist_remote_prefix or "") if config else ""


async def _probe_dir(db: AsyncSession, check_dir: str) -> dict[str, Any]:
    """尝试列出校验目录：返回是否可达、样例文件名与非目录文件数。"""
    try:
        server = await get_active_server(db, None)
        config = await db.scalar(select(OpenListConfig).limit(1))
        api = OpenListAPI(
            server.server_url, server.token or "", verify_ssl=not bool(config and config.disable_ssl_verify)
        )
        result = await api.list_files(check_dir or "/", refresh=True, max_retries=1)
    except Exception as exc:  # noqa: BLE001  目录不可达仅作为警告
        return {"reachable": False, "files": [], "file_count": 0, "error": str(exc)}
    content = result.get("content") or []
    files = [item.get("name", "") for item in content if item and not item.get("is_dir", False)]
    return {"reachable": True, "files": files[:_MAX_SAMPLE_FILES], "file_count": len(files), "error": None}


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def _validate_mode(mode: str) -> None:
    if mode not in _OPENLIST_MODES:
        raise BadRequestException("A 模式仅支持 incremental / full / strm_only")


async def _get_upload_task(db: AsyncSession, task_id: int) -> UploadTask:
    task = await db.get(UploadTask, task_id)
    if task is None:
        raise BadRequestException("绑定的上传任务不存在，请刷新后重新选择")
    return task


async def _get_openlist_task(db: AsyncSession, task_id: int) -> OpenListTask:
    task = await db.get(OpenListTask, task_id)
    if task is None or task.is_deleted:
        raise BadRequestException("绑定的 STRM 任务不存在或已删除，请刷新后重新选择")
    return task


async def _ensure_name_unique(db: AsyncSession, name: str, exclude_id: Optional[int] = None) -> None:
    stmt = select(AutomationTask.id).where(
        AutomationTask.is_deleted.is_(False), AutomationTask.name == name
    )
    if exclude_id is not None:
        stmt = stmt.where(AutomationTask.id != exclude_id)
    if await db.scalar(stmt) is not None:
        raise BadRequestException(f"自动化任务名称「{name}」已存在")


async def _ensure_binding_unique(
    db: AsyncSession,
    upload_task_id: int,
    openlist_task_id: int,
    exclude_id: Optional[int] = None,
) -> None:
    """未删除任务内，一个 B/A 任务只能被一个自动化任务绑定。"""
    stmt = select(AutomationTask).where(AutomationTask.is_deleted.is_(False))
    if exclude_id is not None:
        stmt = stmt.where(AutomationTask.id != exclude_id)
    rows = (await db.scalars(stmt)).all()
    for row in rows:
        if row.upload_task_id == upload_task_id:
            raise BadRequestException(f"上传任务已被自动化任务「{row.name}」绑定")
        if row.openlist_task_id == openlist_task_id:
            raise BadRequestException(f"STRM 任务已被自动化任务「{row.name}」绑定")


async def _validate_mapping(db: AsyncSession, upload_task: UploadTask, check_dir: str) -> str:
    prefix = await _load_remote_prefix(db)
    expected = expected_check_dir(upload_task.remote_dir, prefix)
    normalized = normalize_dir(check_dir)
    if normalized != expected:
        raise BadRequestException(f"校验目录与上传任务目标目录不一致，应填写：{expected or '/'}")
    return normalized


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _pending_count(task: AutomationTask) -> int:
    if not task.pending_files:
        return 0
    try:
        value = json.loads(task.pending_files)
    except (TypeError, ValueError):
        return 0
    return len(value) if isinstance(value, list) else 0


def task_to_dict(
    task: AutomationTask,
    upload_task_name: Optional[str] = None,
    openlist_task_name: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "upload_task_id": task.upload_task_id,
        "upload_task_name": upload_task_name or "",
        "openlist_task_id": task.openlist_task_id,
        "openlist_task_name": openlist_task_name or "",
        "check_dir": task.check_dir,
        "upload_concurrency": task.upload_concurrency,
        "upload_retry_times": task.upload_retry_times,
        "openlist_mode": task.openlist_mode,
        "wait_interval_seconds": task.wait_interval_seconds,
        "openlist_wait_timeout": task.openlist_wait_timeout,
        "idle_wait_timeout": task.idle_wait_timeout,
        "stage_timeout": task.stage_timeout,
        "interval_seconds": task.interval_seconds,
        "pending_file_count": _pending_count(task),
        "last_round_no": task.last_round_no,
        "consecutive_failures": task.consecutive_failures,
        "scan_time": task.scan_time.isoformat(sep=" ") if task.scan_time else None,
        "is_running": registry.is_running(task.id),
        "created_time": task.created_time.isoformat(sep=" ") if task.created_time else None,
        "updated_time": task.updated_time.isoformat(sep=" ") if task.updated_time else None,
    }


async def _name_maps(
    db: AsyncSession, tasks: list[AutomationTask]
) -> tuple[dict[int, str], dict[int, str]]:
    upload_ids = {task.upload_task_id for task in tasks if task.upload_task_id}
    openlist_ids = {task.openlist_task_id for task in tasks if task.openlist_task_id}
    upload_names: dict[int, str] = {}
    openlist_names: dict[int, str] = {}
    if upload_ids:
        rows = (await db.execute(select(UploadTask.id, UploadTask.name).where(UploadTask.id.in_(upload_ids)))).all()
        upload_names = {row[0]: row[1] for row in rows}
    if openlist_ids:
        rows = (
            await db.execute(select(OpenListTask.id, OpenListTask.name).where(OpenListTask.id.in_(openlist_ids)))
        ).all()
        openlist_names = {row[0]: row[1] for row in rows}
    return upload_names, openlist_names


async def _to_dicts(db: AsyncSession, tasks: list[AutomationTask]) -> list[dict[str, Any]]:
    upload_names, openlist_names = await _name_maps(db, tasks)
    return [
        task_to_dict(task, upload_names.get(task.upload_task_id), openlist_names.get(task.openlist_task_id))
        for task in tasks
    ]


# ---------------------------------------------------------------------------
# 任务 CRUD
# ---------------------------------------------------------------------------


async def list_tasks(
    db: AsyncSession, keyword: Optional[str] = None, page: int = 1, page_size: int = 20
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(AutomationTask).where(AutomationTask.is_deleted.is_(False))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                AutomationTask.name.like(like),
                AutomationTask.check_dir.like(like),
            )
        )
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        await db.scalars(stmt.order_by(AutomationTask.id.desc()).offset((page - 1) * page_size).limit(page_size))
    ).all()
    return await _to_dicts(db, list(rows)), total


async def get_task(db: AsyncSession, task_id: int) -> AutomationTask:
    task = await db.get(AutomationTask, task_id)
    if task is None or task.is_deleted:
        raise NotFoundException("自动化任务不存在")
    return task


async def get_task_detail(db: AsyncSession, task_id: int) -> dict[str, Any]:
    task = await get_task(db, task_id)
    return (await _to_dicts(db, [task]))[0]


async def create_task(db: AsyncSession, data: AutomationTaskCreate) -> dict[str, Any]:
    _validate_mode(data.openlist_mode)
    upload_task = await _get_upload_task(db, data.upload_task_id)
    await _get_openlist_task(db, data.openlist_task_id)
    await _ensure_name_unique(db, data.name.strip())
    await _ensure_binding_unique(db, data.upload_task_id, data.openlist_task_id)
    check_dir = await _validate_mapping(db, upload_task, data.check_dir)

    task = AutomationTask(
        name=data.name.strip(),
        upload_task_id=data.upload_task_id,
        openlist_task_id=data.openlist_task_id,
        upload_concurrency=data.upload_concurrency,
        upload_retry_times=data.upload_retry_times,
        openlist_mode=data.openlist_mode,
        check_dir=check_dir,
        wait_interval_seconds=data.wait_interval_seconds,
        openlist_wait_timeout=data.openlist_wait_timeout,
        idle_wait_timeout=data.idle_wait_timeout,
        stage_timeout=data.stage_timeout,
        interval_seconds=data.interval_seconds,
    )
    db.add(task)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise BadRequestException("任务名称或绑定任务已被占用，请刷新后重试")
    await db.refresh(task)

    warnings: list[str] = []
    probe = await _probe_dir(db, check_dir)
    if not probe["reachable"]:
        warnings.append(f"校验目录当前不可访问（{probe['error']}），任务仍可保存，但启动前需确保目录可达")
    result = (await _to_dicts(db, [task]))[0]
    result["warnings"] = warnings
    return result


async def update_task(db: AsyncSession, task_id: int, data: AutomationTaskUpdate) -> dict[str, Any]:
    task = await get_task(db, task_id)
    if registry.is_running(task_id):
        raise BadRequestException("任务正在运行，请先停止后再修改")

    changes = data.model_dump(exclude_unset=True)
    name = (changes.get("name") or task.name).strip()
    upload_task_id = changes.get("upload_task_id", task.upload_task_id)
    openlist_task_id = changes.get("openlist_task_id", task.openlist_task_id)
    mode = changes.get("openlist_mode", task.openlist_mode)
    _validate_mode(mode)

    upload_task = await _get_upload_task(db, upload_task_id)
    await _get_openlist_task(db, openlist_task_id)
    await _ensure_name_unique(db, name, exclude_id=task_id)
    await _ensure_binding_unique(db, upload_task_id, openlist_task_id, exclude_id=task_id)
    check_dir = await _validate_mapping(db, upload_task, changes.get("check_dir", task.check_dir))

    task.name = name
    task.upload_task_id = upload_task_id
    task.openlist_task_id = openlist_task_id
    task.openlist_mode = mode
    task.check_dir = check_dir
    for field in (
        "upload_concurrency",
        "upload_retry_times",
        "wait_interval_seconds",
        "openlist_wait_timeout",
        "idle_wait_timeout",
        "stage_timeout",
        "interval_seconds",
    ):
        if field in changes:
            setattr(task, field, changes[field])
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise BadRequestException("任务名称或绑定任务已被占用，请刷新后重试")
    await db.refresh(task)

    warnings: list[str] = []
    probe = await _probe_dir(db, check_dir)
    if not probe["reachable"]:
        warnings.append(f"校验目录当前不可访问（{probe['error']}），任务仍可保存，但启动前需确保目录可达")
    result = (await _to_dicts(db, [task]))[0]
    result["warnings"] = warnings
    return result


async def delete_task(db: AsyncSession, task_id: int) -> dict[str, Any]:
    task = await get_task(db, task_id)
    if registry.is_running(task_id):
        raise BadRequestException("任务正在运行，请先停止后再删除")
    task.is_deleted = True
    await db.commit()
    return {"id": task_id}


async def batch_delete_tasks(db: AsyncSession, ids: list[int]) -> dict[str, Any]:
    tasks = (await db.scalars(select(AutomationTask).where(AutomationTask.id.in_(ids)))).all()
    found = {task.id: task for task in tasks if not task.is_deleted}
    running = [task.name for task in found.values() if registry.is_running(task.id)]
    if running:
        raise BadRequestException(f"以下任务正在运行，请先停止：{'、'.join(running)}")
    for task in found.values():
        task.is_deleted = True
    await db.commit()
    return {"deleted": len(found), "missing": sorted(set(ids) - set(found))}


# ---------------------------------------------------------------------------
# 绑定选项与校验目录检测
# ---------------------------------------------------------------------------


async def bind_options(db: AsyncSession, include_task_id: Optional[int] = None) -> dict[str, Any]:
    """可选 B/A 任务：排除已被其它自动化任务绑定的任务，并返回推导的校验目录。"""
    prefix = await _load_remote_prefix(db)
    stmt = select(AutomationTask).where(AutomationTask.is_deleted.is_(False))
    if include_task_id is not None:
        stmt = stmt.where(AutomationTask.id != include_task_id)
    bound = (await db.scalars(stmt)).all()
    upload_bound = {row.upload_task_id: row.name for row in bound}
    openlist_bound = {row.openlist_task_id: row.name for row in bound}

    upload_tasks = (await db.scalars(select(UploadTask).order_by(UploadTask.id.desc()))).all()
    openlist_tasks = (
        await db.scalars(
            select(OpenListTask).where(OpenListTask.is_deleted.is_(False)).order_by(OpenListTask.id.desc())
        )
    ).all()
    return {
        "openlist_remote_prefix": prefix,
        "upload_tasks": [
            {
                "id": task.id,
                "name": task.name,
                "remote_dir": task.remote_dir,
                "derived_check_dir": expected_check_dir(task.remote_dir, prefix),
                "bound_by": upload_bound.get(task.id),
            }
            for task in upload_tasks
        ],
        "openlist_tasks": [
            {
                "id": task.id,
                "name": task.name,
                "process_path": task.process_path,
                "output_dir": task.output_dir,
                "bound_by": openlist_bound.get(task.id),
            }
            for task in openlist_tasks
        ],
    }


async def check_dir(db: AsyncSession, data: AutomationCheckDirRequest) -> dict[str, Any]:
    """检测目录映射：规范化输入、返回期望目录、目录样例文件与映射是否一致。"""
    upload_task = await _get_upload_task(db, data.upload_task_id)
    if data.task_id is not None:
        await get_task(db, data.task_id)
    prefix = await _load_remote_prefix(db)
    expected = expected_check_dir(upload_task.remote_dir, prefix)
    normalized = normalize_dir(data.check_dir) or expected
    probe = await _probe_dir(db, normalized)
    consistent = normalized == expected
    if not consistent:
        message = f"目录与上传任务目标目录不一致，建议使用：{expected or '/'}"
    elif probe["reachable"]:
        message = f"目录映射一致，当前可列出 {probe['file_count']} 个文件"
    else:
        message = f"目录映射一致，但当前不可访问：{probe['error']}"
    return {
        "check_dir": normalized,
        "expected_check_dir": expected,
        "consistent": consistent,
        "reachable": probe["reachable"],
        "file_count": probe["file_count"],
        "files": probe["files"],
        "error": probe["error"],
        "message": message,
    }


# ---------------------------------------------------------------------------
# 运行管理：运行态、运行历史、日志（阶段③）
# ---------------------------------------------------------------------------


def run_to_dict(run: AutomationRun, *, upload: Any = None, openlist: Any = None) -> dict[str, Any]:
    """运行记录序列化（时间统一北京时间字符串）。"""
    missed: list[str] = []
    if run.missed_files:
        try:
            data = json.loads(run.missed_files)
            if isinstance(data, list):
                missed = [str(item) for item in data]
        except (TypeError, ValueError):
            missed = []
    return {
        "id": run.id,
        "task_id": run.task_id,
        "task_name": run.task_name,
        "round_no": run.round_no,
        "status": run.status,
        "phase": run.phase,
        "upload_execution_id": run.upload_execution_id,
        "openlist_execution_id": run.openlist_execution_id,
        "new_file_count": run.new_file_count,
        "pending_file_count": run.pending_file_count,
        "checked_file_count": run.checked_file_count,
        "skipped_file_count": run.skipped_file_count,
        "wait_seconds": run.wait_seconds,
        "idle_wait_seconds": run.idle_wait_seconds,
        "missed_files": missed,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "log_path": run.log_path,
        "started_time": _fmt_time(run.started_time),
        "finished_time": _fmt_time(run.finished_time),
        "created_time": _fmt_time(run.created_time),
        "upload": upload,
        "openlist": openlist,
    }


def _fmt_time(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        return value.strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError:  # pragma: no cover
        return str(value)


def _execution_brief(execution: Any, kind: str) -> Optional[dict]:
    """A/B 执行记录的轻量摘要，供运行详情展示。"""
    if execution is None:
        return None
    data = {
        "id": execution.id,
        "status": execution.status,
        "error_code": getattr(execution, "error_code", None),
        "error_message": getattr(execution, "error_message", None),
        "started_time": _fmt_time(getattr(execution, "started_time", None)),
        "finished_time": _fmt_time(getattr(execution, "finished_time", None)),
        "log_path": getattr(execution, "log_path", None),
    }
    if kind == "upload":
        data.update(
            {
                "file_total": getattr(execution, "file_total", 0),
                "file_success": getattr(execution, "file_success", 0),
                "file_skipped": getattr(execution, "file_skipped", 0),
                "file_failed": getattr(execution, "file_failed", 0),
            }
        )
    return data


async def list_runs(
    db: AsyncSession,
    task_id: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    stmt = select(AutomationRun)
    if task_id is not None:
        stmt = stmt.where(AutomationRun.task_id == task_id)
    if status:
        stmt = stmt.where(AutomationRun.status == status)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await db.scalars(
            stmt.order_by(AutomationRun.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return [run_to_dict(run) for run in rows], int(total)


async def get_run_detail(db: AsyncSession, run_id: int) -> dict[str, Any]:
    run = await db.get(AutomationRun, run_id)
    if run is None:
        raise NotFoundException("运行记录不存在")
    upload = openlist = None
    if run.upload_execution_id:
        upload = _execution_brief(await db.get(UploadExecution, run.upload_execution_id), "upload")
    if run.openlist_execution_id:
        openlist = _execution_brief(await db.get(OpenListExecution, run.openlist_execution_id), "openlist")
    return run_to_dict(run, upload=upload, openlist=openlist)


def read_run_logs(run_id: int, offset: int = 0, limit: int = 200) -> dict[str, Any]:
    """读取一轮的日志文件（按行切片），返回 ``{total, lines}``。"""
    path = Path(settings.automation_log_dir) / f"automation_run_{run_id}.log"
    if not path.is_file():
        return {"total": 0, "lines": []}
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:  # pragma: no cover
        return {"total": 0, "lines": []}
    total = len(raw_lines)
    lines = []
    for index, text in enumerate(raw_lines[offset : offset + limit], start=offset):
        level = "info"
        message = text
        if text.startswith("[") and "] [" in text:
            stage = text.find("] [")
            level = text[stage + 3 : text.find("]", stage + 3)].strip().lower()
            message = text[text.find("]", stage + 3) + 1 :].strip()
        elif text.startswith("["):
            message = text[text.find("]") + 1 :].strip()
        lines.append({"index": index, "level": level, "message": message})
    return {"total": total, "lines": lines}


def active_tasks() -> list[dict[str, Any]]:
    """当前进程内运行中的自动化任务（运行态快照）。"""
    result: list[dict[str, Any]] = []
    for task_id in sorted(registry.RUNNING):
        if not registry.is_running(task_id):
            continue
        state = registry.get_runtime(task_id)
        result.append(
            {
                "task_id": task_id,
                "phase": state.get("phase"),
                "run_id": state.get("run_id"),
                "round_no": state.get("round_no"),
                "next_round_at": state.get("next_round_at"),
                "log_path": state.get("log_path"),
                "started_time": state.get("started_time"),
            }
        )
    return result


async def reset_fingerprint(db: AsyncSession, task_id: int) -> dict[str, Any]:
    """重置本地扫描指纹：下一轮无论文件是否变化都会重新触发。"""
    task = await get_task(db, task_id)
    task.scan_fingerprint = None
    task.scan_time = None
    await db.commit()
    return await get_task_detail(db, task_id)


async def clear_pending(db: AsyncSession, task_id: int, remote_names: Optional[list[str]] = None) -> dict[str, Any]:
    """清空待校验文件：给定名单则只移除名单内文件，否则清空全部。"""
    task = await get_task(db, task_id)
    current: list[str] = []
    if task.pending_files:
        try:
            parsed = json.loads(task.pending_files)
            if isinstance(parsed, list):
                current = [str(item) for item in parsed]
        except (TypeError, ValueError):
            current = []
    if remote_names:
        removing = set(remote_names)
        remaining = [name for name in current if name not in removing]
    else:
        remaining = []
    task.pending_files = json.dumps(remaining, ensure_ascii=False) if remaining else None
    if not remaining:
        task.pending_fingerprint = None
    await db.commit()
    return await get_task_detail(db, task_id)


async def retry_failed(db: AsyncSession, run_id: int) -> dict[str, Any]:
    """把一条失败运行的缺失文件写回任务 pending，供新一轮补偿（不自动启动）。"""
    run = await db.get(AutomationRun, run_id)
    if run is None:
        raise NotFoundException("运行记录不存在")
    task = await get_task(db, run.task_id)
    missed: list[str] = []
    if run.missed_files:
        try:
            parsed = json.loads(run.missed_files)
            if isinstance(parsed, list):
                missed = [str(item) for item in parsed]
        except (TypeError, ValueError):
            missed = []
    if not missed and not task.pending_files:
        raise BadRequestException("该运行没有可重试的失败文件")
    existing: list[str] = []
    if task.pending_files:
        try:
            parsed = json.loads(task.pending_files)
            if isinstance(parsed, list):
                existing = [str(item) for item in parsed]
        except (TypeError, ValueError):
            existing = []
    merged = sorted(set(existing) | set(missed))
    task.pending_files = json.dumps(merged, ensure_ascii=False) if merged else None
    await db.commit()
    return await get_task_detail(db, run.task_id)
