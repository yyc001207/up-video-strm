"""上传管理执行引擎：六阶段流水线（扫描 → 过滤 → 重命名 → 清单 → 查重 → 上传）。

``start_execution`` 校验通过后 ``asyncio.create_task`` 启动本模块的
``run_upload``；后者在独立数据库会话中运行（请求会话在端点返回后即关闭）。

约定：
- 取消通过 ``TaskStatusManager`` 以 ``str(execution_id)`` 为键轮询半实时响应；
- 文件级结果写入 ``upload_file_record``，执行级汇总写回 ``upload_execution``；
- 日志只写文件（``settings.upload_log_dir``），同时经 WS 推送 log/progress/status 帧；
- 真实网络调用只在用户触发执行时发生，单元测试以 mock 客户端覆盖。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.business.openlist.task_status_manager import TaskStatusManager
from app.business.uploader import rename_engine, scanner
from app.business.uploader.execution_logger import ExecutionLogHandler, UploadLogPump
from app.business.uploader.pan123_client import Pan123Client
from app.business.uploader.service import build_client, get_access_token
from app.core.database import AsyncSessionLocal
from app.core.exceptions import BadRequestException
from app.core.logger import logger
from app.core.models import OpenListConfig, UploadExecution, UploadFileRecord, UploadTask
from app.core.settings import settings

# 同时运行的上传执行数上限（每个执行内部再按 concurrency 并行上传文件）
_sem: asyncio.Semaphore = asyncio.Semaphore(2)


def set_semaphore_size(size: int) -> None:
    """调整同时运行的上传执行数上限（最小 1）。"""
    global _sem
    _sem = asyncio.Semaphore(max(1, int(size)))


def _build_per_execution_logger(execution_id: int, queue) -> logging.Logger:
    exe_logger = logging.getLogger(f"upload.execution_{execution_id}")
    exe_logger.handlers.clear()
    exe_logger.setLevel(logging.INFO)
    exe_logger.propagate = False
    exe_logger.addHandler(ExecutionLogHandler(queue))
    return exe_logger


@dataclass
class UploadAction:
    """一个待上传文件的决策结果。"""

    record_id: int
    local_path: Path
    remote_name: str
    size: int
    md5: str
    duplicate: int = 1
    replace_file_id: Optional[int] = None


def _suffix_name(name: str, used: set[str]) -> str:
    """为「追加后缀」策略生成不冲突的文件名：``123.mp4`` → ``123_1.mp4``。"""
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        ext = "." + ext
    else:
        stem, ext = name, ""
    index = 1
    candidate = f"{stem}_{index}{ext}"
    while candidate in used:
        index += 1
        candidate = f"{stem}_{index}{ext}"
    return candidate


async def _wait_async_result(client: Pan123Client, token: str, preupload_id: str) -> int:
    """轮询异步上传结果，返回 fileId（最多约 60 秒）。"""
    for _ in range(60):
        result = await client.upload_async_result(token, preupload_id)
        if result.get("completed") or result.get("fileId"):
            return int(result.get("fileId") or 0)
        await asyncio.sleep(1)
    raise BadRequestException("123 云盘异步上传超时")


async def _upload_one(
    client: Pan123Client,
    token: str,
    parent_file_id: int,
    action: UploadAction,
    exe_logger: logging.Logger,
    retry_times: int,
) -> tuple[int, int]:
    """上传单个文件（含重试），返回 ``(fileId, 实际上传字节数)``。"""
    last_exc: Optional[Exception] = None
    for attempt in range(1, retry_times + 2):
        try:
            data = await client.create_file(
                token,
                parent_file_id=parent_file_id,
                filename=action.remote_name,
                etag=action.md5,
                size=action.size,
                duplicate=action.duplicate,
            )
            preupload_id = str(data.get("preuploadID") or "")
            if data.get("reuse") or not preupload_id:
                # 秒传完成：服务端直接返回 fileId
                return int(data.get("fileId") or 0), 0
            slice_size = int(data.get("sliceSize") or 0)
            if slice_size <= 0:
                raise BadRequestException("123 云盘预上传未返回分片大小")

            uploaded = 0
            with open(action.local_path, "rb") as fh:
                slice_no = 1
                while True:
                    chunk = fh.read(slice_size)
                    if not chunk:
                        break
                    url = await client.get_upload_url(token, preupload_id, slice_no)
                    await client.upload_part(url, chunk)
                    uploaded += len(chunk)
                    slice_no += 1

            result = await client.upload_complete(token, preupload_id)
            if result.get("async"):
                file_id = await _wait_async_result(client, token, preupload_id)
            else:
                file_id = int(result.get("fileId") or 0)
            return file_id, uploaded
        except Exception as exc:  # noqa: BLE001 - 重试后统一抛出
            last_exc = exc
            exe_logger.warning("上传 %s 第 %d 次失败：%s", action.remote_name, attempt, exc)
            await asyncio.sleep(min(0.2 * (2 ** (attempt - 1)), 2.0))
    raise last_exc if last_exc else BadRequestException("上传失败")


async def _run_pipeline(
    *,
    execution_id: int,
    exe_logger: logging.Logger,
    progress: dict,
    cancel_key: str,
) -> str:
    """执行六阶段流水线，返回最终状态字符串。"""
    async with AsyncSessionLocal() as db:
        execution = await db.get(UploadExecution, execution_id)
        if execution is None or execution.is_deleted:
            raise BadRequestException("执行记录不存在")
        if execution.status != "running":
            return execution.status
        task = await db.get(UploadTask, execution.task_id)
        if task is None:
            raise BadRequestException("上传任务不存在")
        config = await db.scalar(select(OpenListConfig).order_by(OpenListConfig.id).limit(1))
        extensions = scanner.normalize_extensions(config.video_formats if config else None)

        exe_logger.info(
            "执行开始：任务「%s」%s → %s", execution.task_name, execution.local_dir, execution.remote_dir
        )
        exe_logger.info(
            "参数：季数=%d，源起始集号=%d，冲突策略=%s，并发=%d，重试=%d，试运行=%s",
            execution.season,
            execution.start_episode,
            execution.conflict_policy,
            execution.concurrency,
            execution.retry_times,
            execution.dry_run,
        )

        # 阶段 1–2：扫描 + 视频过滤
        files, scan_errors = scanner.scan_files(execution.local_dir, extensions)
        for path, reason in scan_errors:
            exe_logger.error("扫描失败 %s：%s", path, reason)
            progress["failed"] += 1
        exe_logger.info("扫描完成：识别视频文件 %d 个，异常 %d 个", len(files), len(scan_errors))

        # 阶段 3–4：重命名 + 预上传清单
        template = execution.template or rename_engine.DEFAULT_TEMPLATE
        plan_items: list[tuple[scanner.ScannedFile, rename_engine.RenamePlan, UploadFileRecord]] = []
        records: list[UploadFileRecord] = []
        for scanned in files:
            try:
                plan = rename_engine.plan_rename(
                    scanned.name,
                    season=execution.season,
                    start_episode=execution.start_episode,
                    template=template,
                )
            except rename_engine.RenameError as exc:
                exe_logger.warning("跳过 %s：%s", scanned.name, exc)
                progress["failed"] += 1
                records.append(
                    UploadFileRecord(
                        execution_id=execution.id,
                        local_path=str(scanned.path),
                        remote_name=scanned.name,
                        size=scanned.size,
                        md5=scanned.md5,
                        status="failed",
                        phase="rename",
                        reason=str(exc),
                    )
                )
                continue
            record = UploadFileRecord(
                execution_id=execution.id,
                local_path=str(scanned.path),
                remote_name=plan.output_name,
                size=scanned.size,
                md5=scanned.md5,
                status="pending",
                phase="ready",
            )
            records.append(record)
            plan_items.append((scanned, plan, record))

        for record in records:
            db.add(record)
        await db.commit()
        for record in records:
            await db.refresh(record)
        progress["total"] = len(plan_items) + len(scan_errors)
        exe_logger.info("清单生成完成：待上传 %d 个文件", len(plan_items))

        if not plan_items:
            exe_logger.info("未找到可上传的视频文件")
            return "fail" if progress["failed"] > 0 else "success"

        if execution.dry_run:
            exe_logger.info("试运行：仅生成上传清单，不执行上传")
            progress["skipped"] = len(plan_items)
            return "success"

        # 阶段 5：重复检查（读取云端目标目录）
        client = await build_client(db)
        try:
            token = await get_access_token(db)
            parent_file_id = await client.resolve_dir_path(token, execution.remote_dir)
            remote_items = await client.list_all_files(token, parent_file_id=parent_file_id)
            remote_names = {
                str(item.get("filename")): int(item.get("fileId") or 0)
                for item in remote_items
                if int(item.get("type") or 0) == 0
            }
            exe_logger.info("重复检查完成：云端已有 %d 个同名候选文件", len(remote_names))
        except Exception as exc:
            exe_logger.error("目标目录读取失败：%s", exc)
            for _scanned, _plan, record in plan_items:
                record.status = "failed"
                record.phase = "check"
                record.reason = f"目标目录读取失败：{exc}"
                progress["failed"] += 1
            progress["skipped"] = 0
            await db.commit()
            await client.aclose()
            return "fail"

        # 冲突策略决策（顺序执行，保证后缀名不重复）
        policy = (execution.conflict_policy or "skip").lower()
        used_names: set[str] = set(remote_names)
        actions: list[UploadAction] = []
        for _scanned, plan, record in plan_items:
            name = plan.output_name
            existing = name in remote_names
            if existing and policy == "skip":
                record.status = "skipped"
                record.phase = "check"
                record.reason = "目标目录已存在同名文件"
                progress["skipped"] += 1
                continue
            if existing and policy == "overwrite":
                record.replaced_file_id = remote_names[name]
                actions.append(
                    UploadAction(
                        record_id=record.id,
                        local_path=Path(record.local_path),
                        remote_name=name,
                        size=record.size,
                        md5=record.md5,
                        duplicate=2,
                        replace_file_id=remote_names[name],
                    )
                )
                continue
            if existing and policy == "suffix":
                name = _suffix_name(name, used_names)
                used_names.add(name)
                record.remote_name = name
            actions.append(
                UploadAction(
                    record_id=record.id,
                    local_path=Path(record.local_path),
                    remote_name=name,
                    size=record.size,
                    md5=record.md5,
                    duplicate=1,
                )
            )
        await db.commit()
        exe_logger.info("冲突检查完成：待上传 %d 个，跳过 %d 个", len(actions), progress["skipped"])

        # 阶段 6：上传（受执行参数 concurrency 限制）
        record_by_id = {record.id: record for _s, _p, record in plan_items}
        per_file_sem = asyncio.Semaphore(max(1, int(execution.concurrency or 1)))

        async def _worker(action: UploadAction):
            async with per_file_sem:
                if TaskStatusManager.is_cancelled(cancel_key):
                    return action, "cancelled", 0, 0, "执行已取消"
                progress["current"] = action.remote_name
                try:
                    file_id, uploaded = await _upload_one(
                        client, token, parent_file_id, action, exe_logger, execution.retry_times
                    )
                    return action, "success", file_id, uploaded, ""
                except Exception as exc:  # noqa: BLE001 - 单文件失败不影响其他文件
                    exe_logger.error("上传失败 %s：%s", action.remote_name, exc)
                    return action, "failed", 0, 0, str(exc)

        try:
            results = await asyncio.gather(*[_worker(action) for action in actions])
        finally:
            pass

        cancelled = TaskStatusManager.is_cancelled(cancel_key)
        for action, result_status, file_id, uploaded, reason in results:
            record = record_by_id.get(action.record_id)
            if record is None:
                continue
            record.phase = "upload"
            if result_status == "success":
                record.status = "success"
                record.remote_file_id = file_id or None
                progress["success"] += 1
                progress["bytesUploaded"] += uploaded
                if action.replace_file_id:
                    # 覆盖策略：新文件上传成功后，按旧 fileId 幂等删除兜底
                    try:
                        await client.delete_files(token, [action.replace_file_id])
                    except Exception as exc:  # noqa: BLE001 - 删除失败不影响结果
                        exe_logger.warning("清理被覆盖的旧文件失败（fileId=%s）：%s", action.replace_file_id, exc)
            elif result_status == "skipped":
                record.status = "skipped"
                record.reason = reason
                progress["skipped"] += 1
            else:
                record.status = "failed"
                record.reason = reason
                progress["failed"] += 1
        progress["current"] = ""
        await db.commit()
        await client.aclose()

        if cancelled or TaskStatusManager.is_cancelled(cancel_key):
            return "cancelled"
        if progress["failed"] > 0:
            return "fail"
        return "success"


async def _finish_execution(
    execution_id: int,
    status: str,
    progress: dict,
    duration_seconds: int,
    log_path: str,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            execution = await db.get(UploadExecution, execution_id)
            if execution is None:
                return
            execution.status = status
            execution.file_total = progress.get("total", 0)
            execution.file_success = progress.get("success", 0)
            execution.file_skipped = progress.get("skipped", 0)
            execution.file_failed = progress.get("failed", 0)
            execution.bytes_uploaded = progress.get("bytesUploaded", 0)
            execution.duration_seconds = duration_seconds
            execution.finished_time = datetime.now()
            execution.log_path = log_path
            await db.commit()
    except Exception as exc:
        logger.error(f"上传执行结果回写失败 execution={execution_id}: {exc}")


async def run_upload(*, execution_id: int) -> None:
    """后台运行一次上传执行（由 ``start_execution`` 创建任务）。"""
    sem = _sem
    await sem.acquire()
    cancel_key = str(execution_id)
    TaskStatusManager.clear(cancel_key)
    started = time.monotonic()

    log_path = ""
    try:
        log_dir = Path(settings.upload_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = str(log_dir / f"execution_{execution_id}.log")
    except Exception:
        log_path = ""

    queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
    exe_logger = _build_per_execution_logger(execution_id, queue)
    progress = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "bytesUploaded": 0, "current": ""}
    pump = UploadLogPump(execution_id, queue, log_path, progress)
    pump_task = asyncio.create_task(pump.run())

    status = "success"
    try:
        status = await _run_pipeline(
            execution_id=execution_id, exe_logger=exe_logger, progress=progress, cancel_key=cancel_key
        )
        if TaskStatusManager.is_cancelled(cancel_key) and status == "running":
            status = "cancelled"
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:  # noqa: BLE001 - 统一回写失败状态
        status = "fail"
        exe_logger.error("上传执行失败：%s", exc)
        logger.exception(f"上传执行异常 execution={execution_id}")

    duration = int(time.monotonic() - started)
    try:
        await asyncio.wait_for(pump.stop(), timeout=5)
    except Exception:
        pass
    try:
        await asyncio.wait_for(pump_task, timeout=10)
    except Exception:
        pump_task.cancel()

    await _finish_execution(execution_id, status, progress, duration, log_path)
    try:
        await pump.write_status(status)
    except Exception:
        pass
    try:
        exe_logger.handlers.clear()
    except Exception:
        pass
    sem.release()
