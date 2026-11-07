"""自动化任务：执行引擎（阶段③，模块 C 的核心状态机）。

一轮链路的固定顺序：

1. 扫描本地目录得到 stat 指纹 F（始终执行）；
2. ``pending_files`` 非空 → 跳过 B，直接做 OpenList 可见性校验（补偿轮）；
3. 否则 F 与已提交指纹相同（且非手动强制轮）→ 本轮无变更，不建 run；
4. 建 run → 等 A/B 空闲 → 触发 B（冲突策略固定 skip）→ 等 OpenList 可见 →
   触发 A → A 成功则清空 pending 并提交指纹；失败保留 pending，下轮补偿。

失败分级：配置类错误立即终止；轮次失败（B/A 失败、可见性超时、阶段超时）按
``consecutive_failures`` 累计，连续 3 次终止；轮次之间按 ``interval_seconds``
指数退避（封顶 300s）。进程退出/重启不恢复运行，残留 running 由启动清理置为
``PROCESS_RESTART``。
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.business.automation import adapters, registry
from app.business.automation.change_detector import compute_fingerprint
from app.business.automation.execution_logger import AutomationLogger, broadcast_notice
from app.business.automation.notifier import notify_abnormal
from app.business.automation.relay import ExecutionLogRelay
from app.business.openlist.openlist_api import OpenListAPI
from app.business.openlist import service as openlist_service
from app.business.uploader.scanner import normalize_extensions
from app.core.beijing import BEIJING_TZ, beijing_now
from app.core.database import AsyncSessionLocal
from app.core.exceptions import BadRequestException
from app.core.logger import logger
from app.core.models.automation.task import AutomationTask
from app.core.models.automation.run import AutomationRun
from app.core.models.openlist.config import OpenListConfig
from app.core.models.openlist.task import OpenListTask
from app.core.models.uploader.task import UploadTask

POLL_INTERVAL_SECONDS = 2.0
CANCEL_GRACE_SECONDS = 30.0
MAX_CONSECUTIVE_FAILURES = 3
MAX_ROUND_BACKOFF_SECONDS = 300
MAX_MISSED_FILES = 200
MAX_DELAY_SECONDS = 60.0

#: 手动启动强制一轮（跳指纹检查），首轮后自动失效
_FORCE: dict[int, bool] = {}


def parse_pending(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if item]


def dump_pending(names: list[str]) -> Optional[str]:
    unique = sorted({str(name) for name in names if name})
    return json.dumps(unique, ensure_ascii=False) if unique else None


@dataclass
class Snapshot:
    """一轮执行需要的任务配置快照（不持有 ORM 对象）。"""

    task_id: int
    task_name: str
    upload_task_id: int
    openlist_task_id: int
    local_dir: str
    check_dir: str
    mode: str
    concurrency: int
    retry_times: int
    interval_seconds: int
    wait_interval_seconds: int
    openlist_wait_timeout: int
    idle_wait_timeout: int
    stage_timeout: int
    scan_fingerprint: Optional[str]
    pending: list[str] = field(default_factory=list)
    extensions: tuple = ()


async def _load_snapshot(task_id: int) -> Optional[Snapshot]:
    async with AsyncSessionLocal() as db:
        task = await db.get(AutomationTask, task_id)
        if task is None or task.is_deleted:
            return None
        upload_task = await db.get(UploadTask, task.upload_task_id)
        openlist_task = await db.get(OpenListTask, task.openlist_task_id)
        if upload_task is None or openlist_task is None or openlist_task.is_deleted:
            return None
        config = await db.scalar(select(OpenListConfig).order_by(OpenListConfig.id).limit(1))
        return Snapshot(
            task_id=task.id,
            task_name=task.name,
            upload_task_id=task.upload_task_id,
            openlist_task_id=task.openlist_task_id,
            local_dir=upload_task.local_dir,
            check_dir=task.check_dir,
            mode=task.openlist_mode,
            concurrency=task.upload_concurrency,
            retry_times=task.upload_retry_times,
            interval_seconds=task.interval_seconds,
            wait_interval_seconds=task.wait_interval_seconds,
            openlist_wait_timeout=task.openlist_wait_timeout,
            idle_wait_timeout=task.idle_wait_timeout,
            stage_timeout=task.stage_timeout,
            scan_fingerprint=task.scan_fingerprint,
            pending=parse_pending(task.pending_files),
            extensions=normalize_extensions(config.video_formats if config else None),
        )


async def _sleep(task_id: int, seconds: float) -> bool:
    """可被停止事件打断的等待；返回 False 表示已请求停止。"""
    event = registry.get_stop_event(task_id)
    if event.is_set():
        return False
    try:
        await asyncio.wait_for(event.wait(), timeout=max(0.1, seconds))
        return False
    except asyncio.TimeoutError:
        return True


async def _update_task(task_id: int, **fields) -> None:
    async with AsyncSessionLocal() as db:
        task = await db.get(AutomationTask, task_id)
        if task is None:
            return
        for key, value in fields.items():
            setattr(task, key, value)
        await db.commit()


async def _update_run(run_id: int, **fields) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(AutomationRun, run_id)
        if run is None:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        await db.commit()


async def _finish_run(run_id: int, log: AutomationLogger, status: str, **fields) -> None:
    """写入 run 终态，并广播带 ``pending`` 的 status 帧（页面操作栏实时归零）。"""
    await _update_run(run_id, status=status, phase="done", finished_time=beijing_now(), **fields)
    pending = fields.get("pending_file_count")
    if pending is None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AutomationRun.pending_file_count).where(AutomationRun.id == run_id))
            value = result.scalar_one_or_none()
        pending = 0 if value is None else int(value)
    await log.status(status=status, run_id=run_id, phase="done", pending=pending)


# ---------- 对外入口 ----------


async def start_task(task_id: int, *, force_round: bool = True) -> None:
    """启动一个自动化任务实例（同任务仅一个）。"""
    if registry.is_running(task_id):
        raise BadRequestException("任务正在运行")
    _FORCE[task_id] = force_round
    event = registry.get_stop_event(task_id)
    event.clear()
    instance = asyncio.create_task(_run_loop(task_id), name=f"automation-task-{task_id}")
    registry.register(task_id, instance)
    registry.set_runtime(
        task_id,
        phase="starting",
        run_id=None,
        round_no=0,
        next_round_at=None,
        log_path=None,
        started_time=beijing_now().strftime("%Y-%m-%d %H:%M:%S"),
    )


async def stop_task(task_id: int) -> dict:
    if not registry.is_running(task_id):
        raise BadRequestException("任务未在运行")
    registry.request_stop(task_id)
    return {"stopping": True}


def is_running(task_id: int) -> bool:
    return registry.is_running(task_id)


async def _run_loop(task_id: int) -> None:
    try:
        await _loop(task_id)
    except asyncio.CancelledError:  # pragma: no cover - 应用退出
        raise
    except Exception:  # noqa: BLE001 - 兜底避免实例静默死亡
        logger.exception("自动化任务 %s 运行实例异常退出", task_id)
    finally:
        _FORCE.pop(task_id, None)
        registry.unregister(task_id)
        registry.clear_runtime(task_id)
        try:
            await _update_task(task_id, updated_time=beijing_now())
        except Exception:  # pragma: no cover
            pass


async def _loop(task_id: int) -> None:
    while True:
        if registry.stop_requested(task_id):
            return
        snapshot = await _load_snapshot(task_id)
        if snapshot is None:
            logger.warning("自动化任务 %s 不存在或绑定任务已删除，停止运行", task_id)
            return

        fingerprint, file_count, scan_errors, ignored_partial = compute_fingerprint(
            snapshot.local_dir, snapshot.extensions
        )
        pending = snapshot.pending
        force = _FORCE.pop(task_id, False)

        if pending:
            outcome = await _execute_round(
                snapshot, fingerprint, file_count, scan_errors, ignored_partial, pending, force=False
            )
        elif file_count == 0:
            await _update_task(task_id, scan_fingerprint=fingerprint, scan_time=beijing_now(), pending_files=None)
            if ignored_partial:
                await broadcast_notice(
                    task_id,
                    "info",
                    f"忽略下载中文件 {ignored_partial} 个（下载完成后会自动纳入下一轮）",
                )
            await _set_runtime_sleep(task_id, "idle", snapshot.interval_seconds)
            if not await _sleep(task_id, snapshot.interval_seconds):
                return
            continue
        elif not force and fingerprint == snapshot.scan_fingerprint:
            await _set_runtime_sleep(task_id, "idle", snapshot.interval_seconds)
            if not await _sleep(task_id, snapshot.interval_seconds):
                return
            continue
        else:
            outcome = await _execute_round(
                snapshot, fingerprint, file_count, scan_errors, ignored_partial, pending, force=force
            )

        status = outcome["status"]
        if status in ("success", "partial"):
            if outcome.get("failed_files"):
                await _update_task(
                    task_id,
                    consecutive_failures=0,
                    scan_fingerprint=fingerprint,
                    scan_time=beijing_now(),
                    pending_files=None,
                )
            else:
                await _update_task(
                    task_id,
                    consecutive_failures=0,
                    scan_fingerprint=outcome.get("committed_fingerprint") or fingerprint,
                    scan_time=beijing_now(),
                )
            if registry.stop_requested(task_id):
                return
            await _set_runtime_sleep(task_id, "interval", snapshot.interval_seconds)
            if not await _sleep(task_id, snapshot.interval_seconds):
                return
            continue

        if status == "cancelled":
            return

        # fail：累计连续失败并退避
        failures = await _bump_failures(task_id)
        fatal = bool(outcome.get("fatal"))
        if fatal or failures >= MAX_CONSECUTIVE_FAILURES:
            message = outcome.get("message") or "自动化任务连续失败"
            if failures >= MAX_CONSECUTIVE_FAILURES and not fatal:
                message = f"连续 {failures} 轮失败，已停止：{message}"
            await notify_abnormal(task_id, snapshot.task_name, message)
            await _set_runtime_sleep(task_id, "stopped", None)
            return
        backoff = min(snapshot.interval_seconds * (2**failures), MAX_ROUND_BACKOFF_SECONDS)
        await _set_runtime_sleep(task_id, "backoff", backoff, last_error=outcome.get("error_code"))
        if not await _sleep(task_id, backoff):
            return


async def _bump_failures(task_id: int) -> int:
    async with AsyncSessionLocal() as db:
        task = await db.get(AutomationTask, task_id)
        if task is None:
            return MAX_CONSECUTIVE_FAILURES
        task.consecutive_failures = (task.consecutive_failures or 0) + 1
        await db.commit()
        return task.consecutive_failures


async def _set_runtime_sleep(task_id: int, phase: str, seconds: Optional[int], **extra) -> None:
    next_at = None
    if seconds:
        next_at = datetime.fromtimestamp(beijing_now().timestamp() + seconds, BEIJING_TZ).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    registry.set_runtime(task_id, phase=phase, next_round_at=next_at, **extra)


# ---------- 单轮执行 ----------


async def _execute_round(
    snapshot: Snapshot,
    fingerprint: str,
    file_count: int,
    scan_errors: list[str],
    ignored_partial: int,
    pending: list[str],
    *,
    force: bool,
) -> dict:
    """执行一轮，返回 ``{status, error_code, message, fatal, committed_fingerprint}``。"""
    async with AsyncSessionLocal() as db:
        task = await db.get(AutomationTask, snapshot.task_id)
        round_no = (task.last_round_no if task else 0) + 1
        if task is not None:
            task.last_round_no = round_no
            await db.commit()
    async with AsyncSessionLocal() as db:
        run = AutomationRun(
            task_id=snapshot.task_id,
            task_name=snapshot.task_name,
            round_no=round_no,
            status="running",
            phase="waiting_idle",
            started_time=beijing_now(),
            pending_file_count=len(pending),
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    log = AutomationLogger(snapshot.task_id, run_id)
    registry.set_runtime(snapshot.task_id, run_id=run_id, phase="waiting_idle", round_no=round_no, log_path=log.log_path)
    await log.status(status="running", run_id=run_id, round_no=round_no, phase="waiting_idle")
    await log.info(
        f"第 {round_no} 轮开始：本地视频 {file_count} 个，待校验 {len(pending)} 个"
        + (f"，忽略下载中文件 {ignored_partial} 个" if ignored_partial else "")
        + ("（手动强制一轮）" if force else "")
    )
    for message in scan_errors:
        await log.warning(f"扫描异常：{message}")

    uploaded_names: list[str] = []
    b_partial = False
    b_skipped = 0
    committed_fingerprint = fingerprint

    try:
        # 阶段 1：等 A/B 空闲
        idle_started = time.monotonic()
        idle_status = await _wait_idle(snapshot, log)
        if idle_status == "cancelled":
            await _finish_run(run_id, log, "cancelled", error_code="B_CANCELLED", error_message="用户停止")
            return {"status": "cancelled"}
        if idle_status == "timeout":
            message = f"等待 A/B 空闲超过 {snapshot.idle_wait_timeout} 秒"
            await log.error(message)
            await _finish_run(
                run_id, log,
                "fail",
                error_code="IDLE_TIMEOUT",
                error_message=message[:500],
                idle_wait_seconds=int(time.monotonic() - idle_started),
            )
            return {"status": "fail", "error_code": "IDLE_TIMEOUT", "message": message, "fatal": False}
        await _update_run(run_id, idle_wait_seconds=int(time.monotonic() - idle_started))

        # 阶段 2：B 上传（pending 非空时跳过，做补偿）
        if not pending:
            await _set_phase(run_id, snapshot.task_id, "waiting_upload", log)
            b_result = await _run_upload_stage(snapshot, run_id, log)
            b_status = b_result["status"]
            await _update_run(
                run_id,
                upload_execution_id=b_result.get("execution_id"),
                skipped_file_count=b_result.get("file_skipped", 0),
            )
            if b_status == "cancelled":
                await _finish_run(run_id, log, "cancelled", error_code="B_CANCELLED", error_message="用户停止")
                return {"status": "cancelled"}
            if b_status == "fail" and b_result.get("fatal"):
                await _finish_run(
                    run_id, log,
                    "fail",
                    error_code=b_result.get("error_code") or "B_SCAN_ERROR",
                    error_message=(b_result.get("message") or "上传扫描失败")[:500],
                )
                return {
                    "status": "fail",
                    "error_code": b_result.get("error_code"),
                    "message": b_result.get("message"),
                    "fatal": True,
                }
            if b_status == "fail":
                if not pending and (b_result.get("file_success", 0) + b_result.get("file_skipped", 0)) == 0:
                    message = b_result.get("message") or "上传失败，本轮无任何进展"
                    await log.error(message)
                    await _finish_run(
                        run_id, log,
                        "fail",
                        error_code=b_result.get("error_code") or "B_CLOUD_ERROR",
                        error_message=message[:500],
                    )
                    return {
                        "status": "fail",
                        "error_code": b_result.get("error_code") or "B_CLOUD_ERROR",
                        "message": message,
                        "fatal": False,
                    }
                b_partial = True

            uploaded_names = []
            if b_result.get("execution_id"):
                async with AsyncSessionLocal() as db:
                    uploaded_names = await adapters.uploaded_names(db, b_result["execution_id"])
            pending = sorted(set(pending) | set(uploaded_names))
            b_skipped = b_result.get("file_skipped", 0)
            await _update_task(
                snapshot.task_id,
                pending_files=dump_pending(pending),
                pending_fingerprint=fingerprint,
            )
            await _update_run(run_id, new_file_count=len(uploaded_names), pending_file_count=len(pending))
            await log.info(
                f"上传完成：成功 {b_result.get('file_success', 0)} 个，跳过 {b_skipped} 个，"
                f"失败 {b_result.get('file_failed', 0)} 个；待校验 {len(pending)} 个"
            )
            if not pending:
                await log.info("本轮没有需要校验的新文件，跳过 A 调度")
                await _finish_run(run_id, log, "success", pending_file_count=0)
                return {
                    "status": "success",
                    "committed_fingerprint": fingerprint,
                    "failed_files": b_partial,
                }

        # 阶段 3：OpenList 可见性校验
        await _set_phase(run_id, snapshot.task_id, "waiting_openlist_check", log)
        check_started = time.monotonic()
        check_status, missing, wait_seconds = await _wait_visible(snapshot, pending, log)
        await _update_run(
            run_id,
            checked_file_count=len(pending) - len(missing),
            wait_seconds=int(wait_seconds),
            pending_file_count=len(pending),
        )
        if check_status == "cancelled":
            await _finish_run(run_id, log, "cancelled", error_code="A_CANCELLED", error_message="用户停止")
            return {"status": "cancelled"}
        if check_status == "invalid_dir":
            message = f"校验目录不可访问：{snapshot.check_dir}"
            await log.error(message)
            await _finish_run(run_id, log, "fail", error_code="CHECK_DIR_INVALID", error_message=message[:500])
            await notify_abnormal(snapshot.task_id, snapshot.task_name, message)
            return {"status": "fail", "error_code": "CHECK_DIR_INVALID", "message": message, "fatal": True}
        if check_status == "timeout":
            message = f"等待 OpenList 可见超时，缺失 {len(missing)} 个文件"
            await log.warning(message)
            await _update_task(snapshot.task_id, pending_files=dump_pending(pending))
            await _finish_run(
                run_id, log,
                "fail",
                error_code="OPENLIST_TIMEOUT",
                error_message=message[:500],
                missed_files=json.dumps(missing[:MAX_MISSED_FILES], ensure_ascii=False) if missing else None,
            )
            return {
                "status": "fail",
                "error_code": "OPENLIST_TIMEOUT",
                "message": message,
                "fatal": False,
            }

        # 阶段 4：触发 A 调度
        await _set_phase(run_id, snapshot.task_id, "waiting_openlist_task", log)
        a_result = await _run_openlist_stage(snapshot, run_id, log)
        await _update_run(run_id, openlist_execution_id=a_result.get("execution_id"), pending_file_count=len(pending))
        if a_result["status"] == "cancelled":
            await _finish_run(run_id, log, "cancelled", error_code="A_CANCELLED", error_message="用户停止")
            return {"status": "cancelled"}
        if a_result["status"] == "fail":
            message = a_result.get("message") or "STRM 任务执行失败"
            await log.error(message)
            await _finish_run(
                run_id, log,
                "fail",
                error_code=a_result.get("error_code") or "A_FAILED",
                error_message=message[:500],
                pending_file_count=len(pending),
            )
            return {
                "status": "fail",
                "error_code": a_result.get("error_code") or "A_FAILED",
                "message": message,
                "fatal": False,
            }

        committed_fingerprint = fingerprint
        await _update_task(
            snapshot.task_id,
            pending_files=None,
            pending_fingerprint=None,
            consecutive_failures=0,
        )
        await log.info("A 调度成功，本轮链路完成，已清空待校验文件")
        await _finish_run(
            run_id, log,
            "partial" if b_partial else "success",
            pending_file_count=0,
            skipped_file_count=b_skipped,
        )
        return {
            "status": "partial" if b_partial else "success",
            "committed_fingerprint": committed_fingerprint,
            "failed_files": b_partial,
        }
    except Exception as exc:  # noqa: BLE001 - 单轮异常记录后按轮次失败处理
        logger.exception("自动化任务 %s 第 %s 轮异常", snapshot.task_id, run_id)
        await log.error(f"本轮异常：{exc}")
        await _finish_run(run_id, log, "fail", error_code="INTERNAL_ERROR", error_message=str(exc)[:500])
        return {"status": "fail", "error_code": "INTERNAL_ERROR", "message": str(exc), "fatal": False}


async def _set_phase(run_id: int, task_id: int, phase: str, log: AutomationLogger) -> None:
    await _update_run(run_id, phase=phase)
    registry.set_runtime(task_id, phase=phase)
    await log.status(status="running", run_id=run_id, phase=phase)


async def _wait_idle(snapshot: Snapshot, log: AutomationLogger) -> str:
    started = time.monotonic()
    deadline = started + snapshot.idle_wait_timeout
    while True:
        if registry.stop_requested(snapshot.task_id):
            return "cancelled"
        if not adapters.is_upload_active(snapshot.upload_task_id) and not adapters.is_openlist_active(
            snapshot.openlist_task_id
        ):
            return "ok"
        if time.monotonic() >= deadline:
            return "timeout"
        if not await _sleep(snapshot.task_id, POLL_INTERVAL_SECONDS):
            return "cancelled"


async def _run_upload_stage(snapshot: Snapshot, run_id: int, log: AutomationLogger) -> dict:
    execution_id = await _start_with_busy_wait(
        snapshot,
        log,
        starter=lambda db: adapters.start_upload(
            db,
            task_id=snapshot.upload_task_id,
            concurrency=snapshot.concurrency,
            retry_times=snapshot.retry_times,
            trigger_ref=f"automation_run:{run_id}",
            trigger_name=snapshot.task_name,
        ),
        label="上传任务",
    )
    if isinstance(execution_id, dict):
        return execution_id  # 已失败/取消
    await _update_run(run_id, upload_execution_id=execution_id)
    return await _wait_execution(
        snapshot,
        log,
        execution_id=execution_id,
        kind="upload",
        label="上传",
    )


async def _run_openlist_stage(snapshot: Snapshot, run_id: int, log: AutomationLogger) -> dict:
    execution_id = await _start_with_busy_wait(
        snapshot,
        log,
        starter=lambda db: adapters.start_openlist(
            db,
            task_id=snapshot.openlist_task_id,
            mode=snapshot.mode,
            trigger_ref=f"automation_run:{run_id}",
            trigger_name=snapshot.task_name,
        ),
        label="STRM 任务",
    )
    if isinstance(execution_id, dict):
        return execution_id
    await _update_run(run_id, openlist_execution_id=execution_id)
    return await _wait_execution(
        snapshot,
        log,
        execution_id=execution_id,
        kind="openlist",
        label="STRM",
    )


async def _start_with_busy_wait(snapshot: Snapshot, log: AutomationLogger, *, starter, label: str) -> int | dict:
    """启动 A/B 执行；遇到「任务正在执行」时继续等待（不计失败），超阶段超时返回失败。"""
    started = time.monotonic()
    while True:
        if registry.stop_requested(snapshot.task_id):
            return {"status": "cancelled"}
        try:
            async with AsyncSessionLocal() as db:
                return await starter(db)
        except BadRequestException as exc:
            if "正在执行" not in str(exc):
                message = f"{label}无法启动：{exc}"
                await log.error(message)
                return {"status": "fail", "error_code": "CONFIG_INVALID", "message": message, "fatal": True}
            if time.monotonic() - started >= snapshot.stage_timeout:
                message = f"等待{label}空闲超时"
                await log.error(message)
                return {"status": "fail", "error_code": "STAGE_TIMEOUT", "message": message, "fatal": False}
            if not await _sleep(snapshot.task_id, POLL_INTERVAL_SECONDS):
                return {"status": "cancelled"}
        except Exception as exc:  # noqa: BLE001 - 启动异常按配置类错误处理
            message = f"{label}启动失败：{exc}"
            await log.error(message)
            return {"status": "fail", "error_code": "CONFIG_INVALID", "message": message, "fatal": True}


async def _wait_execution(snapshot: Snapshot, log: AutomationLogger, *, execution_id: int, kind: str, label: str) -> dict:
    """轮询 A/B 执行直到终态；期间把 A/B 日志镜像进当前轮次日志。"""
    prefix = f"{'B' if kind == 'upload' else 'A'}#{execution_id}"
    relay = ExecutionLogRelay(log, prefix)
    relay_task = asyncio.create_task(relay.run())
    try:
        return await _wait_execution_inner(
            snapshot,
            log,
            relay,
            execution_id=execution_id,
            kind=kind,
            label=label,
        )
    finally:
        relay.stop()
        try:
            await asyncio.wait_for(relay_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):  # pragma: no cover - 兜底
            relay_task.cancel()


async def _wait_execution_inner(
    snapshot: Snapshot,
    log: AutomationLogger,
    relay: ExecutionLogRelay,
    *,
    execution_id: int,
    kind: str,
    label: str,
) -> dict:
    """``_wait_execution`` 的实现体；阶段超时先取消，宽限 30s 后仍活跃则记 STAGE_TIMEOUT。"""
    started = time.monotonic()
    deadline = started + snapshot.stage_timeout
    while True:
        if registry.stop_requested(snapshot.task_id):
            async with AsyncSessionLocal() as db:
                if kind == "upload":
                    await adapters.cancel_upload(db, execution_id)
                else:
                    await adapters.cancel_openlist(db, execution_id)
            return {"status": "cancelled", "execution_id": execution_id}
        async with AsyncSessionLocal() as db:
            result = (
                await adapters.upload_result(db, execution_id)
                if kind == "upload"
                else await adapters.openlist_result(db, execution_id)
            )
        if result is None:
            return {"status": "fail", "execution_id": execution_id, "error_code": "INTERNAL_ERROR", "message": "执行记录不存在"}
        relay.set_path(result.get("log_path"))
        if result["status"] in adapters.TERMINAL_STATUSES:
            result["execution_id"] = execution_id
            if result["status"] == "fail":
                result.setdefault("message", result.get("error_message") or f"{label}执行失败")
            return result
        if time.monotonic() >= deadline:
            message = f"{label}执行超过阶段超时 {snapshot.stage_timeout} 秒"
            await log.warning(message)
            async with AsyncSessionLocal() as db:
                if kind == "upload":
                    await adapters.cancel_upload(db, execution_id)
                else:
                    await adapters.cancel_openlist(db, execution_id)
            grace_deadline = time.monotonic() + CANCEL_GRACE_SECONDS
            while time.monotonic() < grace_deadline:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                async with AsyncSessionLocal() as db:
                    final = (
                        await adapters.upload_result(db, execution_id)
                        if kind == "upload"
                        else await adapters.openlist_result(db, execution_id)
                    )
                if final is None or final["status"] in adapters.TERMINAL_STATUSES:
                    break
            else:
                await log.error(f"{label}执行取消后仍未退出，标记 orphan")
            return {
                "status": "fail",
                "execution_id": execution_id,
                "error_code": "STAGE_TIMEOUT",
                "message": message,
                "orphan": True,
            }
        if not await _sleep(snapshot.task_id, POLL_INTERVAL_SECONDS):
            continue


async def _wait_visible(snapshot: Snapshot, pending: list[str], log: AutomationLogger) -> tuple[str, list[str], float]:
    """等待 pending 文件在 OpenList 的 check_dir 中可见；返回 ``(状态, 缺失列表, 等待秒数)``。"""
    async with AsyncSessionLocal() as db:
        server = await openlist_service.get_active_server(db)
        verify_ssl = await openlist_service._get_verify_ssl(db)  # noqa: SLF001 - 复用 A 模块配置
    api = OpenListAPI(server.server_url, server.token or "", verify_ssl=verify_ssl)
    started = time.monotonic()
    deadline = started + snapshot.openlist_wait_timeout
    delay = float(snapshot.wait_interval_seconds)
    refresh = False
    missing = list(pending)
    while True:
        if registry.stop_requested(snapshot.task_id):
            return "cancelled", missing, time.monotonic() - started
        try:
            data = await api.list_files(snapshot.check_dir, refresh=refresh, max_retries=2)
            content = data.get("content") or []
            names = {str(item.get("name")) for item in content if not item.get("is_dir")}
            missing = [name for name in pending if name not in names]
            await log.progress(
                phase="waiting_openlist_check",
                pending=len(pending),
                checked=len(pending) - len(missing),
            )
            if not missing:
                return "ok", [], time.monotonic() - started
        except Exception as exc:  # noqa: BLE001 - 逐次重试，超时由外层判定
            if "not found" in str(exc).lower():
                return "invalid_dir", missing, time.monotonic() - started
            await log.warning(f"OpenList 目录读取失败，稍后重试：{exc}")
        if time.monotonic() >= deadline:
            return "timeout", missing, time.monotonic() - started
        jitter = random.uniform(0.8, 1.2)
        if not await _sleep(snapshot.task_id, delay * jitter):
            return "cancelled", missing, time.monotonic() - started
        delay = min(delay * 2, MAX_DELAY_SECONDS)
        refresh = True
