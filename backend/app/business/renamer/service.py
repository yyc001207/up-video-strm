"""本地改名：扫描计划缓存、重命名执行与操作日志。

设计要点：
- 扫描结果按根目录缓存，执行时只允许重命名扫描结果中存在的文件（防止越权改名）；
- 目标文件夹必须位于扫描根目录内（分季移动的安全边界）；
- 所有操作写入 ``settings.rename_log_dir/rename.log``，并在内存保留最近 1000 条供页面展示。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from collections import OrderedDict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.business.renamer import planner
from app.core.settings import settings

logger = logging.getLogger(__name__)

MAX_BATCH = 500
_PLAN_LIMIT = 20
CONFLICT_MODES = {"skip", "overwrite", "autonum"}

_plans: "OrderedDict[str, dict[str, dict]]" = OrderedDict()
_plans_lock = threading.Lock()

_recent_logs: deque[dict[str, Any]] = deque(maxlen=1000)
_logs_lock = threading.Lock()


# ---------------------------------------------------------------- 日志


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_file_path() -> Path:
    return Path(settings.rename_log_dir) / "rename.log"


def add_log(level: str, message: str, detail: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """记录一条操作日志：内存最近记录 + 追加写入日志文件。"""
    entry = {"ts": _timestamp(), "level": level, "message": message, "detail": detail or None}
    with _logs_lock:
        _recent_logs.append(entry)
    try:
        path = log_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        suffix = f" | {json.dumps(detail, ensure_ascii=False)}" if detail else ""
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{entry['ts']}] [{level.upper()}] {message}{suffix}\n")
    except OSError:
        logger.warning("写入本地改名日志失败", exc_info=True)
    return entry


def recent_logs(limit: int = 200) -> list[dict[str, Any]]:
    """返回最近的操作日志（最新在前）。"""
    with _logs_lock:
        items = list(_recent_logs)
    return list(reversed(items[-max(1, limit):]))


# ---------------------------------------------------------------- 扫描


def _clean_path_input(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _resolve_root(input_path: str) -> Path:
    text = _clean_path_input(input_path)
    if not text:
        raise ValueError("请输入文件夹路径")
    root = Path(text).expanduser().resolve()
    if root.parent == root:
        raise ValueError("不允许选择磁盘根目录，请选择具体的文件夹")
    if not root.exists():
        raise ValueError(f"路径不存在: {root}")
    if not root.is_dir():
        raise ValueError(f"路径不是文件夹: {root}")
    return root


def _remember_plan(root: Path, plan: dict) -> None:
    files_by_key: dict[str, dict] = {}
    for show in plan["shows"]:
        for season in show["seasons"]:
            for item in season["files"]:
                files_by_key[f'{item["folder"]}\u0000{item["name"]}'] = item
    with _plans_lock:
        _plans[str(root)] = files_by_key
        _plans.move_to_end(str(root))
        while len(_plans) > _PLAN_LIMIT:
            _plans.popitem(last=False)


def scan_folder(input_path: str) -> dict[str, Any]:
    """扫描文件夹并缓存重命名计划（同步实现，供线程调用）。"""
    root = _resolve_root(input_path)
    try:
        plan = planner.scan_root(root)
    except ValueError as exc:
        add_log("error", "扫描失败", {"path": str(root), "error": str(exc)})
        raise
    _remember_plan(root, plan)
    add_log(
        "info",
        f'扫描完成：{plan["stats"]["shows"]} 个剧集 / {plan["stats"]["files"]} 个文件',
        {"path": str(root)},
    )
    return plan


# ---------------------------------------------------------------- 重命名执行


def _find_existing(folder: Path, target_name: str) -> Optional[str]:
    """Windows 下按大小写不敏感查找同名文件，返回磁盘上的实际名称或 None。"""
    if os.name == "nt":
        try:
            names = [entry.name for entry in os.scandir(folder)]
        except OSError:
            return None
        lowered = target_name.lower()
        return next((name for name in names if name.lower() == lowered), None)
    candidate = folder / target_name
    return target_name if candidate.exists() else None


def _rename_one(folder: Path, src_name: str, dst_folder: Path, dst_name: str, mode: str) -> dict[str, Any]:
    """重命名（或同盘移动）单个文件；目标文件夹不存在时自动创建。"""
    if folder == dst_folder and src_name == dst_name:
        return {"name": src_name, "new_name": dst_name, "status": "skipped", "reason": "已是目标名称"}
    moving = folder != dst_folder
    src = folder / src_name
    dst = dst_folder / dst_name
    try:
        dst_folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"name": src_name, "new_name": dst_name, "status": "failed", "reason": f"无法创建目标文件夹: {exc}"}

    existing = _find_existing(dst_folder, dst_name)
    if existing is not None:
        if not moving and existing.lower() == src_name.lower():
            # 目标即源文件本身（仅大小写不同）：借助临时文件名两步重命名
            temp = folder / f".uvstrm-rename-{uuid.uuid4().hex[:8]}{Path(src_name).suffix}"
            os.replace(src, temp)
            try:
                os.replace(temp, dst)
            except OSError:
                if temp.exists():
                    os.replace(temp, src)
                raise
            return {"name": src_name, "new_name": dst_name, "status": "renamed", "note": "大小写调整"}
        target_path = dst_folder / existing
        if target_path.is_dir():
            return {"name": src_name, "new_name": dst_name, "status": "failed", "reason": f"目标名称已被文件夹占用（{existing}）"}
        if mode == "skip":
            return {"name": src_name, "new_name": dst_name, "status": "skipped", "reason": f"目标文件已存在（{existing}）"}
        if mode == "overwrite":
            target_path.unlink(missing_ok=True)
            os.replace(src, dst)
            note = f"已覆盖 {existing}"
            if moving:
                note += f"（已移动至 {dst_folder.name}）"
            return {"name": src_name, "new_name": dst_name, "status": "renamed", "note": note}
        # autonum: S01E01.mp4 -> S01E01 (2).mp4
        stem = Path(dst_name).stem
        suffix = Path(dst_name).suffix
        for index in range(2, 1000):
            candidate = f"{stem} ({index}){suffix}"
            if _find_existing(dst_folder, candidate) is None:
                os.replace(src, dst_folder / candidate)
                note = "自动编号避免冲突"
                if moving:
                    note += f"（已移动至 {dst_folder.name}）"
                return {"name": src_name, "new_name": candidate, "status": "renamed", "note": note}
        raise ValueError("自动编号重试次数过多，请检查文件夹内容")

    os.replace(src, dst)
    result: dict[str, Any] = {"name": src_name, "new_name": dst_name, "status": "renamed"}
    if moving:
        result["note"] = f"已移动至 {dst_folder.name}"
    return result


def rename_files(
    root_input: str,
    entries: list[dict[str, Any]],
    conflict_mode: str,
    keep_lang: bool,
) -> list[dict[str, Any]]:
    """执行一批重命名（同步实现，供线程调用）。"""
    root = Path(_clean_path_input(root_input) or ".").expanduser().resolve()
    with _plans_lock:
        plan = _plans.get(str(root))
    if plan is None:
        raise ValueError("请先扫描该文件夹后再执行重命名")
    if conflict_mode not in CONFLICT_MODES:
        raise ValueError("无效的冲突处理模式")
    if not isinstance(entries, list) or not entries:
        raise ValueError("没有待重命名的文件")
    if len(entries) > MAX_BATCH:
        raise ValueError(f"单次最多重命名 {MAX_BATCH} 个文件，请分批执行")
    keep_lang_on = keep_lang is not False

    results: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            results.append({"name": "", "new_name": "", "status": "failed", "reason": "条目格式无效"})
            continue
        try:
            folder = Path(str(raw.get("folder") or "")).expanduser().resolve()
        except (OSError, ValueError):
            results.append({"name": str(raw.get("name") or ""), "new_name": "", "status": "failed", "reason": "文件夹路径无效"})
            continue
        name = str(raw.get("name") or "")
        item = plan.get(f"{folder}\u0000{name}")
        if item is None:
            results.append({"name": name, "new_name": name, "status": "failed", "reason": "文件不在扫描结果中，已拒绝（请重新扫描）"})
            continue

        episode = item["episode"] if item["episode"] is not None else (item["auto_number"] or 1)
        computed = planner.build_new_name(item["season"], episode, item["ext"], item["lang_tag"] if keep_lang_on else None)
        new_name = computed
        custom = raw.get("new_name")
        if isinstance(custom, str) and custom.strip():
            candidate = custom.strip()
            if planner.is_valid_target_name(candidate):
                new_name = candidate
            else:
                results.append(
                    {
                        "name": name,
                        "new_name": candidate,
                        "status": "failed",
                        "reason": "自定义目标名称无效（为空、含非法字符或为系统保留名）",
                    }
                )
                continue

        target_folder_raw = raw.get("target_folder")
        if isinstance(target_folder_raw, str) and target_folder_raw.strip():
            target_folder = Path(target_folder_raw.strip()).expanduser().resolve()
        else:
            target_folder = folder
        if not planner.is_inside(root, target_folder):
            results.append({"name": name, "new_name": new_name, "status": "failed", "reason": "目标文件夹不在扫描目录内，已拒绝"})
            continue

        try:
            results.append(_rename_one(folder, name, target_folder, new_name, conflict_mode))
        except (OSError, ValueError) as exc:
            results.append({"name": name, "new_name": new_name, "status": "failed", "reason": str(exc)})

    renamed = sum(1 for result in results if result["status"] == "renamed")
    skipped = sum(1 for result in results if result["status"] == "skipped")
    failed = sum(1 for result in results if result["status"] == "failed")
    add_log(
        "warn" if failed else "info",
        f"重命名批次完成：成功 {renamed}，跳过 {skipped}，失败 {failed}",
        {"path": str(root), "mode": conflict_mode},
    )
    return results


# ---------------------------------------------------------------- 异步包装（接口层使用）


async def scan_async(input_path: str) -> dict[str, Any]:
    return await asyncio.to_thread(scan_folder, input_path)


async def rename_async(
    root_input: str,
    entries: list[dict[str, Any]],
    conflict_mode: str,
    keep_lang: bool,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(rename_files, root_input, entries, conflict_mode, keep_lang)
