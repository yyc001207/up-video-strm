"""自动化任务：本地目录变更检测（阶段③）。

只看 stat（路径 + 大小 + mtime_ns），不读文件内容、不算 MD5：一轮里既要反复
扫描，又不能因为大文件读取拖慢链路。扫描范围与上传模块保持一致：
按全局「视频格式」过滤、跳过隐藏文件与系统文件、递归子目录。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable

from app.business.uploader.scanner import is_partial_file, normalize_extensions

_SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}


def _is_skipped(name: str) -> bool:
    return name.startswith(".") or name.lower() in _SKIP_NAMES


def collect_stats(local_dir: str, extensions: object = None) -> tuple[list[tuple[str, int, int]], list[str], int]:
    """返回 ``([(绝对路径, 大小, mtime_ns)], [错误说明], 忽略的下载中文件数)``；目录不可读不抛异常。"""
    root = Path(local_dir).expanduser()
    if not root.is_dir():
        return [], [f"本地目录不存在或不是文件夹：{root}"], 0

    allowed = set(normalize_extensions(extensions))
    entries: list[tuple[str, int, int]] = []
    errors: list[str] = []
    ignored_partial = 0

    def _walk(directory: Path) -> None:
        nonlocal ignored_partial
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if _is_skipped(entry.name):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            _walk(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            if is_partial_file(entry.name):
                                ignored_partial += 1
                                continue
                            ext = Path(entry.name).suffix.lower().lstrip(".")
                            if ext not in allowed:
                                continue
                            stat = entry.stat()
                            entries.append((str(entry.path), stat.st_size, stat.st_mtime_ns))
                    except OSError as exc:  # pragma: no cover - 权限/占用异常
                        errors.append(f"{entry.path} 读取失败：{exc}")
        except OSError as exc:  # pragma: no cover - 目录权限异常
            errors.append(f"{directory} 读取失败：{exc}")

    _walk(root)
    entries.sort(key=lambda item: item[0])
    return entries, errors, ignored_partial


def fingerprint_of(entries: Iterable[tuple[str, int, int]]) -> str:
    """把 stat 列表折叠成 SHA1 指纹；空列表返回空集指纹。"""
    digest = hashlib.sha1()
    for path, size, mtime_ns in entries:
        digest.update(f"{path}\0{size}\0{mtime_ns}\n".encode("utf-8", "replace"))
    return digest.hexdigest()


def compute_fingerprint(local_dir: str, extensions: object = None) -> tuple[str, int, list[str], int]:
    """返回 ``(指纹, 视频文件数, 错误列表, 忽略的下载中文件数)``。"""
    entries, errors, ignored_partial = collect_stats(local_dir, extensions)
    return fingerprint_of(entries), len(entries), errors, ignored_partial
