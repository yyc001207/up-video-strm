"""上传管理：本地文件扫描（执行阶段 1–2）。

遍历任务本地目录（``recursive`` 控制是否递归），按全局配置的「视频格式」过滤，
跳过隐藏/系统文件，计算文件大小与 MD5（分块读取，不整文件载入内存）。

扫描不中断：单个文件读取失败会进入 ``errors`` 列表，由执行引擎记录为失败。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_VIDEO_EXTENSIONS = ("mp4", "mkv", "avi", "wmv", "flv", "mov", "webm", "ts")
"""全局「视频格式」未配置时的兜底扩展名列表。"""

_SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ScannedFile:
    """一个通过格式过滤的本地视频文件。"""

    path: Path
    name: str
    ext: str
    size: int
    md5: str


def normalize_extensions(raw: object) -> tuple[str, ...]:
    """把「mp4,mkv,avi」字符串或列表规范化为小写、去点的扩展名元组。"""
    if raw is None:
        return DEFAULT_VIDEO_EXTENSIONS
    if isinstance(raw, str):
        items: Iterable[str] = raw.split(",")
    elif isinstance(raw, (list, tuple, set)):
        items = [str(item) for item in raw]
    else:
        return DEFAULT_VIDEO_EXTENSIONS
    extensions: list[str] = []
    for item in items:
        ext = str(item).strip().lower().lstrip(".")
        if ext and ext not in extensions:
            extensions.append(ext)
    return tuple(extensions or DEFAULT_VIDEO_EXTENSIONS)


def file_md5(path: Path) -> str:
    """分块计算 MD5（123 云盘的 etag 参数使用文件内容 MD5）。"""
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_skipped(name: str) -> bool:
    return name.startswith(".") or name.lower() in _SKIP_NAMES


def scan_files(
    local_dir: str,
    extensions: object = None,
    *,
    recursive: bool = True,
) -> tuple[list[ScannedFile], list[tuple[str, str]]]:
    """扫描本地目录，返回 ``(视频文件列表, [(路径, 失败原因)])``。

    - 目录不存在/不可读 → 直接返回单条错误，不抛异常，由调用方决定执行失败；
    - 非视频扩展名、隐藏/系统文件 → 跳过且不算错误；
    - 单个文件读取失败（权限/占用等）→ 记入错误列表，继续扫描。
    """
    root = Path(local_dir).expanduser()
    if not root.is_dir():
        return [], [(str(root), "本地目录不存在或不是文件夹")]

    allowed = set(normalize_extensions(extensions))
    files: list[ScannedFile] = []
    errors: list[tuple[str, str]] = []

    def _iter_entries(directory: Path, recurse: bool) -> Iterable[Path]:
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if _is_skipped(entry.name):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recurse:
                                yield from _iter_entries(Path(entry.path), recurse)
                        elif entry.is_file(follow_symlinks=False):
                            yield Path(entry.path)
                    except OSError as exc:  # pragma: no cover - 目录权限异常
                        errors.append((str(entry.path), f"读取失败：{exc}"))
        except OSError as exc:
            errors.append((str(directory), f"读取失败：{exc}"))

    for file_path in _iter_entries(root, recursive):
        ext = file_path.suffix.lower().lstrip(".")
        if ext not in allowed:
            continue
        try:
            size = file_path.stat().st_size
            md5 = file_md5(file_path)
        except OSError as exc:
            errors.append((str(file_path), f"读取失败：{exc}"))
            continue
        files.append(ScannedFile(path=file_path, name=file_path.name, ext=ext, size=size, md5=md5))

    files.sort(key=lambda item: item.name.lower())
    return files, errors


def find_remote_dir_id(items: list[dict], name: str) -> Optional[int]:
    """在 123 云盘目录列表里按名称查找子目录 fileId（不区分大小写）。"""
    lowered = name.lower()
    for item in items:
        if int(item.get("type") or 0) == 1 and str(item.get("filename") or "").lower() == lowered:
            return int(item.get("fileId") or 0)
    return None
