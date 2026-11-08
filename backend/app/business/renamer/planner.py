"""剧集文件批量重命名：纯逻辑（目录结构识别、集数/季数提取、目标名计算、冲突标记）。

本模块不依赖数据库与网络，便于单元测试；重命名执行与日志见 ``service.py``。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional

VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".ts", ".m2ts", ".mts",
    ".webm", ".rmvb", ".rm", ".mpg", ".mpeg", ".m4v", ".3gp", ".ogm", ".strm",
}
SUB_EXTS = {".srt", ".ass", ".ssa", ".sub", ".smi", ".vtt", ".idx", ".sup", ".lrc"}

# 常见字幕语言标记（重命名时保留，如 S01E01.chs.srt）
LANG_TAGS = {
    "chs", "cht", "chi", "zho", "zh", "zh-cn", "zh-tw", "zh-hk", "zh-hans",
    "zh-hant", "cmn", "yue", "cn", "hk", "tw", "hans", "hant", "trad", "sim",
    "en", "eng", "ja", "jp", "jpn", "ko", "kor", "kr", "fr", "fra", "fre",
    "de", "deu", "ger", "es", "spa", "ru", "rus", "pt", "por", "it", "ita",
    "ar", "ara", "th", "tha", "vi", "vie", "tr", "tur", "nl", "pl", "sv",
    "da", "fi", "no", "he", "id", "ms", "hi", "ta", "fa", "uk", "cs", "hu",
    "ro", "el", "bg", "sr", "hr", "sk", "sl", "lt", "lv", "et", "big5", "gb", "sc", "tc",
}

IGNORED_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}

# 画质/编码/音轨标记：提取集数前先剔除，避免被误判为集数（4K→4、HDR10→10、DDP5.1→5）。
# 用字母数字边界而非 \b——下划线会把 "4K_EA" 连成一个单词导致 \b4k\b 无法匹配。
_QUALITY_TOKEN_RE = re.compile(
    "|".join(
        [
            r"(?<![a-z0-9])(?:4k|2k|8k|2160p|1080p|720p|480p|576p|uhd|fhd|hd|sd|sdr|3d|hdr10\+?|hdr|dolby\s*vision|dv)(?![a-z0-9])",
            r"(?<![a-z0-9])(?:hevc|avc|x26[45]|h26[45]|10bit|8bit|hi10p)(?![a-z0-9])",
            r"(?<![a-z0-9])(?:web-?dl|webrip|blu-?ray|remux|hdtv|hdrip|bdrip|dvdrip)(?![a-z0-9])",
            r"(?<![a-z0-9])(?:ddp?|eac3|ac3|aac|dts(?:-hd|-x)?|truehd|atmos|flac|opus|pcm)\s*\d*(?:\.\d+)?(?:ch|声道)?(?![a-z0-9])",
            r"(?<![a-z0-9])ea(?![a-z0-9])",
            r"(?<!\w)(?:2\.0|2\.1|4\.1|5\.1|6\.1|7\.1)(?!\w)",
        ]
    ),
    re.IGNORECASE,
)

_EPISODE_PATTERNS = [
    re.compile(r"s\s*\d{1,2}\s*e\s*p?\s*(\d{1,4})", re.IGNORECASE),  # S01E01 / S1EP01
    re.compile(r"\bepisode\s*(\d{1,4})\b", re.IGNORECASE),  # Episode 01
    re.compile(r"\bep\s*(\d{1,4})\b", re.IGNORECASE),  # EP01
    re.compile(r"\be\s*(\d{1,4})\b", re.IGNORECASE),  # E01
    re.compile(r"第\s*(\d{1,4})\s*[集话話]"),  # 第01集
    re.compile(r"\[(\d{1,4})\]"),  # [01]
    re.compile(r"\((\d{1,4})\)"),  # (01)
]

_FALLBACK_EPISODE_RE = re.compile(r"(?:^|[^\d])(\d{1,4})(?:[^\d]|$)")
_HALF_EPISODE_RE = re.compile(r"(?:^|[^\d.])\d{1,4}\.5\b")

_SEASON_PATTERNS = [
    re.compile(r"^s\s*(\d{1,2})(?:$|[\s._\-\[\]])", re.IGNORECASE),  # S01 / s2 / S1.xxx
    re.compile(r"^season\s*(\d{1,2})(?:$|[\s._\-\[\]])", re.IGNORECASE),  # Season 1
    re.compile(r"^第\s*(\d{1,2})\s*季"),  # 第1季
]

_RESOLUTION_NUMBERS = {1080, 1440, 2160, 3840, 4320, 7680}

_ILLEGAL_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED_STEMS = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)


def _natural_key(name: str) -> list:
    """按数字自然排序的文件名键（01 排在 2 前）。"""
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]


def ext_of(name: str) -> str:
    return Path(name).suffix.lower()


def base_no_ext(name: str) -> str:
    return Path(name).stem


def pad2(value: int) -> str:
    return f"{value:02d}"


# ---------------------------------------------------------------- 识别函数


def extract_episode(file_name_no_ext: str) -> Optional[int]:
    """从去掉扩展名的文件名中提取集数；无法识别返回 None。"""
    cleaned = _QUALITY_TOKEN_RE.sub(" ", str(file_name_no_ext or "").strip()).strip()
    if not cleaned:
        return None
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            number = int(match.group(1))
            if 0 <= number <= 9999:
                return number
    match = _FALLBACK_EPISODE_RE.search(cleaned)
    if match:
        number = int(match.group(1))
        if is_likely_year(number):
            return None
        if number in _RESOLUTION_NUMBERS:
            return None
        return number
    return None


def is_likely_year(number: int) -> bool:
    """1900~2099 视为年份，避免被误判为集数。"""
    return 1900 <= number <= 2099


def extract_season(dir_name: str) -> Optional[int]:
    """从文件夹名提取季数（S01 / Season 1 / 第1季 / 纯数字）。"""
    text = str(dir_name or "").strip()
    if not text:
        return None
    for pattern in _SEASON_PATTERNS:
        match = pattern.search(text)
        if match:
            return int(match.group(1))
    if re.fullmatch(r"\d{1,2}", text):
        return int(text)
    return None


def detect_lang_tag(file_name_no_ext: str) -> Optional[str]:
    """检测字幕文件名末尾的语言标记（仅最后一个点分段）。"""
    parts = str(file_name_no_ext or "").split(".")
    if len(parts) < 2:
        return None
    last = parts[-1].strip()
    tokens = [token for token in re.split(r"[&_\-]", last.lower()) if token]
    if not tokens or not all(token in LANG_TAGS for token in tokens):
        return None
    return last


def is_half_episode(file_name_no_ext: str) -> bool:
    """检测 .5 特殊集数（5.5 / E05.5 / 第12.5集），需要用户手动输入目标编号。"""
    return bool(_HALF_EPISODE_RE.search(str(file_name_no_ext or "")))


def pair_key(name: str, lang_tag: Optional[str]) -> str:
    """配对键：去掉扩展名与语言标记后的小写文件名（视频与字幕共用编号）。"""
    text = base_no_ext(name).lower()
    if lang_tag:
        suffix = "." + str(lang_tag).lower()
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def build_new_name(season: Optional[int], episode: Optional[int], ext_str: str, lang_tag: Optional[str]) -> str:
    lang = f".{lang_tag}" if lang_tag else ""
    return f"S{pad2(season if season is not None else 1)}E{pad2(episode if episode is not None else 1)}{lang}{ext_str}"


def is_valid_target_name(name: str) -> bool:
    """校验目标文件名：非空、不含路径分隔符与 Windows 非法字符、非系统保留名。"""
    if not isinstance(name, str):
        return False
    text = name.strip()
    if not text or len(text) > 255:
        return False
    if _ILLEGAL_NAME_RE.search(text):
        return False
    if text in {".", ".."} or text.endswith("."):
        return False
    stem = text[: text.rfind(".")] if "." in text else text
    return not _RESERVED_STEMS.match(stem)


def is_inside(root: Path, target: Path) -> bool:
    """判断目标路径是否位于扫描根目录内（移动文件的安全边界）。"""
    try:
        relative = target.relative_to(root)
    except ValueError:
        return False
    return ".." not in relative.parts


# ---------------------------------------------------------------- 目录扫描


def _classify_entries(entries: Iterable[os.DirEntry]) -> dict:
    media_files: list[os.DirEntry] = []
    season_dirs: list[os.DirEntry] = []
    other_dirs: list[os.DirEntry] = []
    other_files: list[os.DirEntry] = []
    for entry in entries:
        if entry.name.lower() in IGNORED_NAMES:
            continue
        try:
            is_dir = entry.is_dir()
        except OSError:
            continue
        if is_dir:
            if extract_season(entry.name) is not None:
                season_dirs.append(entry)
            else:
                other_dirs.append(entry)
        else:
            suffix = ext_of(entry.name)
            if suffix in VIDEO_EXTS or suffix in SUB_EXTS:
                media_files.append(entry)
            else:
                other_files.append(entry)
    return {
        "media_files": media_files,
        "season_dirs": season_dirs,
        "other_dirs": other_dirs,
        "other_files": other_files,
    }


def _read_dir_entries(dir_path: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(dir_path) as iterator:
            return list(iterator)
    except FileNotFoundError as exc:
        raise ValueError(f"无法读取文件夹（路径不存在）: {dir_path}") from exc
    except PermissionError as exc:
        raise ValueError(f"无法读取文件夹（没有访问权限）: {dir_path}") from exc
    except OSError as exc:
        raise ValueError(f"无法读取文件夹（{exc}）: {dir_path}") from exc


def build_file_items(entries: list[os.DirEntry], season: int, folder_path: Path) -> list[dict]:
    """生成一个季（或一级剧集）文件夹内的文件条目，含集数提取、自动编号与冲突标记。"""
    items: list[dict] = []
    for entry in entries:
        name = entry.name
        suffix = ext_of(name)
        no_ext = base_no_ext(name)
        is_sub = suffix in SUB_EXTS
        items.append(
            {
                "name": name,
                "folder": str(folder_path),
                "season": season,
                "ext": suffix,
                "kind": "sub" if is_sub else "video",
                "episode": extract_episode(no_ext),
                "auto_number": None,
                "lang_tag": detect_lang_tag(no_ext) if is_sub else None,
                "half": is_half_episode(no_ext),
                "renumber": None,
                "new_name": None,
                "status": "ok",
                "conflict_with": None,
            }
        )
    items.sort(key=lambda item: _natural_key(item["name"]))

    # 无法识别集数的文件：按文件名自然排序，在已识别最大集数之后依次自动编号
    max_episode = 0
    for item in items:
        if item["episode"] is not None and item["episode"] > max_episode:
            max_episode = item["episode"]
    next_number = max_episode + 1
    for item in items:
        if item["episode"] is None:
            item["auto_number"] = next_number
            next_number += 1

    # “从头开始”模式使用的顺序编号：按自然排序从头编号，配对键相同的视频与字幕共用编号
    renumber_map: dict[str, int] = {}
    next_renumber = 1
    for item in items:
        key = pair_key(item["name"], item["lang_tag"])
        if key not in renumber_map:
            renumber_map[key] = next_renumber
            next_renumber += 1
        item["renumber"] = renumber_map[key]

    # 预览目标名（默认保留语言标记；执行时按界面选项重算）
    for item in items:
        episode = item["episode"] if item["episode"] is not None else item["auto_number"]
        item["new_name"] = build_new_name(item["season"], episode, item["ext"], item["lang_tag"])

    # 冲突标记（仅预览提示；执行时以磁盘实际情况为准）
    lower_names = {item["name"].lower() for item in items}
    for item in items:
        name = item["name"]
        new_name = item["new_name"]
        if name == new_name:
            item["status"] = "noop"
            continue
        if name.lower() == new_name.lower():
            item["status"] = "caseonly"
            continue
        other = next((candidate for candidate in items if candidate["name"].lower() == new_name.lower()), None)
        if other is not None:
            item["conflict_with"] = other["name"]
            item["status"] = "chain" if other["name"] != other["new_name"] else "exists"
    seen: dict[str, str] = {}
    for item in items:
        if item["status"] != "ok":
            continue
        key = item["new_name"].lower()
        if key in seen:
            item["status"] = "duplicate"
            item["conflict_with"] = seen[key]
        else:
            seen[key] = item["name"]
    return items


def _build_show(
    root_path: Path,
    show_name: str,
    media_files: list[os.DirEntry],
    season_dirs: list[os.DirEntry],
    other_dirs: list[os.DirEntry],
    other_files: list[os.DirEntry],
) -> dict:
    show = {"name": show_name, "path": str(root_path), "level": 1, "seasons": [], "warnings": []}
    if other_files:
        names = "、".join(entry.name for entry in other_files[:3])
        suffix = f"（{names}）" if len(other_files) <= 3 else ""
        show["warnings"].append(f"已忽略 {len(other_files)} 个非媒体文件{suffix}")
    if other_dirs:
        show["warnings"].append("已忽略未识别季数的子文件夹: " + "、".join(entry.name for entry in other_dirs))
    if season_dirs:
        show["level"] = 2
        for season_dir in sorted(season_dirs, key=lambda entry: _natural_key(entry.name)):
            season_number = extract_season(season_dir.name) or 1
            folder_path = root_path / season_dir.name
            season = {
                "season": season_number,
                "folder_name": season_dir.name,
                "folder_path": str(folder_path),
                "files": [],
                "warnings": [],
            }
            try:
                classified = _classify_entries(_read_dir_entries(folder_path))
                if classified["other_files"]:
                    season["warnings"].append(f"已忽略 {len(classified['other_files'])} 个非媒体文件")
                if classified["other_dirs"]:
                    season["warnings"].append(
                        "已忽略子文件夹: " + "、".join(entry.name for entry in classified["other_dirs"])
                    )
                if not classified["media_files"]:
                    season["warnings"].append("该季文件夹内未发现视频或字幕文件")
                season["files"] = build_file_items(classified["media_files"], season_number, folder_path)
            except ValueError as exc:
                season["warnings"].append(f"无法读取该季文件夹: {exc}")
            show["seasons"].append(season)
        if media_files:
            show["warnings"].append(f"检测到季文件夹（二级结构），剧集文件夹根目录下的 {len(media_files)} 个媒体文件将被忽略")
    elif media_files:
        show["seasons"].append(
            {
                "season": 1,
                "folder_name": None,
                "folder_path": str(root_path),
                "files": build_file_items(media_files, 1, root_path),
                "warnings": [],
            }
        )
    else:
        show["level"] = 0
        show["warnings"].append("未发现视频/字幕文件或季文件夹，无法识别该文件夹结构")
    return show


def scan_root(root_path: Path) -> dict:
    """扫描根目录：识别其中的所有剧集文件夹（一级/二级结构）。"""
    classified = _classify_entries(_read_dir_entries(root_path))
    shows: list[dict] = []
    warnings: list[str] = []
    root_is_show = bool(classified["media_files"]) or bool(classified["season_dirs"])

    if root_is_show:
        shows.append(
            _build_show(
                root_path,
                root_path.name or str(root_path),
                classified["media_files"],
                classified["season_dirs"],
                [],
                classified["other_files"],
            )
        )
    elif classified["other_files"]:
        warnings.append(f"已忽略根目录下的 {len(classified['other_files'])} 个非媒体文件")

    for entry in classified["other_dirs"]:
        folder_path = root_path / entry.name
        try:
            child = _classify_entries(_read_dir_entries(folder_path))
            shows.append(
                _build_show(
                    folder_path,
                    entry.name,
                    child["media_files"],
                    child["season_dirs"],
                    child["other_dirs"],
                    child["other_files"],
                )
            )
        except ValueError as exc:
            warnings.append(f'无法读取文件夹 "{entry.name}": {exc}')

    shows.sort(key=lambda show: _natural_key(show["name"]))

    stats = {
        "shows": len(shows),
        "seasons": 0,
        "files": 0,
        "unrecognized": 0,
        "conflicts": 0,
        "noop": 0,
        "half_episodes": 0,
    }
    for show in shows:
        for season in show["seasons"]:
            stats["seasons"] += 1
            stats["files"] += len(season["files"])
            for item in season["files"]:
                if item["episode"] is None:
                    stats["unrecognized"] += 1
                if item["status"] in {"duplicate", "chain", "exists"}:
                    stats["conflicts"] += 1
                if item["status"] == "noop":
                    stats["noop"] += 1
                if item["half"]:
                    stats["half_episodes"] += 1
    return {"root": str(root_path), "root_name": root_path.name or str(root_path), "shows": shows, "warnings": warnings, "stats": stats}
