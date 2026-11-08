"""上传管理：字幕文件配对与目标命名。

约定（与用户确认）：

- 只上传与视频**同目录**的字幕，未匹配的字幕不随本次上传；
- 匹配优先级：① 视频主干前缀一致（``Show.S01E03.mkv`` 配 ``Show.S01E03.chs.ass``）；
  ② 同目录下集数相同（走与视频相同的集数解析，含任务自定义 ``episode_pattern``），
  取与字幕名公共前缀最长的视频；
- 目标文件名保留字幕语言标记：``S01E03.chs.ass``（同集多语言不会互相覆盖）；
- 字幕与视频同批上传、各自独立记录，单个字幕失败不影响视频，反之亦然。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from app.business.uploader import rename_engine, scanner

SUBTITLE_EXTENSIONS = ("srt", "ass", "ssa", "vtt", "sub", "idx", "sup")
"""随视频一起上传的字幕扩展名（固定，不随全局「视频格式」变化）。"""

LANG_TAGS = frozenset(
    {
        "chs", "cht", "chi", "zh", "zh-cn", "zh-tw", "zh-hans", "zh-hant",
        "sc", "tc", "gb", "big5", "en", "eng", "jp", "jpn", "ja", "kor", "kr", "ko",
        "简", "繁", "简中", "繁中", "简体", "繁体", "中字", "繁字", "双语", "双字",
        "sdh", "forced", "default",
    }
)
"""可识别的字幕语言/属性标记（小写）。"""


@dataclass(frozen=True)
class SubtitlePlan:
    """一个字幕文件的上传计划。"""

    subtitle: scanner.ScannedFile
    video: scanner.ScannedFile
    plan: rename_engine.RenamePlan
    tag: str
    target_name: str


def _stem(name: str) -> str:
    """去掉扩展名的文件名部分。"""
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


def _is_lang_token(token: str) -> bool:
    """是否为语言标记（支持 ``eng&chs`` 这类组合标记）。"""
    lowered = token.lower()
    if lowered in LANG_TAGS:
        return True
    if "&" in lowered:
        return all(part in LANG_TAGS for part in lowered.split("&") if part)
    return False


def detect_lang_tag(stem: str) -> Optional[str]:
    """取文件名末尾连续的语言标记，例如 ``Show.S01E03.chs.eng`` → ``chs.eng``。"""
    parts = stem.split(".")
    tags: list[str] = []
    for part in reversed(parts):
        if _is_lang_token(part):
            tags.insert(0, part)
        else:
            break
    return ".".join(tags) if tags else None


def build_target_name(video_output_name: str, tag: str, subtitle_ext: str) -> str:
    """由视频目标名生成字幕目标名：``S01E03.mp4`` + ``chs`` → ``S01E03.chs.ass``。"""
    stem = video_output_name.rsplit(".", 1)[0] if "." in video_output_name else video_output_name
    suffix = f".{tag}" if tag else ""
    return f"{stem}{suffix}.{subtitle_ext}"


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index].lower() == right[index].lower():
        index += 1
    return index


def _prefix_tag(sub_stem: str, video_stem: str) -> Optional[str]:
    """按「视频主干前缀」规则取语言标记；不匹配返回 ``None``。

    - 字幕主干与视频主干完全相同 → ``""``（无语言标记）；
    - 字幕主干以 ``视频主干.`` 开头且剩余部分是语言标记 → 返回该标记；
    - 其余（含剩余部分不是语言标记）→ ``None``，交给集数兜底。
    """
    if sub_stem.lower() == video_stem.lower():
        return ""
    if not sub_stem.lower().startswith(video_stem.lower() + "."):
        return None
    remainder = sub_stem[len(video_stem) + 1 :]
    if not remainder:
        return ""
    parts = remainder.split(".")
    if all(_is_lang_token(part) for part in parts):
        return remainder
    return None


def pair_subtitles(
    videos: Iterable[tuple[scanner.ScannedFile, rename_engine.RenamePlan]],
    subtitle_files: Iterable[scanner.ScannedFile],
    episode_pattern: str | None = None,
) -> tuple[list[SubtitlePlan], list[scanner.ScannedFile]]:
    """把字幕配对到同目录视频，返回 ``(字幕计划列表, 未匹配字幕列表)``。

    同一个目标名（忽略大小写）只保留第一个，其余计入未匹配，避免云端互相覆盖。
    """
    video_items = list(videos)
    videos_by_dir: dict[Path, list[tuple[scanner.ScannedFile, rename_engine.RenamePlan]]] = {}
    for scanned, plan in video_items:
        videos_by_dir.setdefault(scanned.path.parent, []).append((scanned, plan))

    plans: list[SubtitlePlan] = []
    used_targets: set[str] = set()
    unmatched: list[scanner.ScannedFile] = []

    for subtitle in sorted(subtitle_files, key=lambda item: item.name.lower()):
        candidates = videos_by_dir.get(subtitle.path.parent)
        if not candidates:
            unmatched.append(subtitle)
            continue
        sub_stem = _stem(subtitle.name)
        matched: Optional[tuple[scanner.ScannedFile, rename_engine.RenamePlan, str]] = None

        # 规则①：视频主干前缀一致（取最长主干，避免 Show 与 Show.S01E03 同时命中）
        for scanned, plan in sorted(candidates, key=lambda item: len(_stem(item[0].name)), reverse=True):
            tag = _prefix_tag(sub_stem, _stem(scanned.name))
            if tag is not None:
                matched = (scanned, plan, tag)
                break

        # 规则②：同集数兜底（自定义集数正则与视频解析保持一致）
        if matched is None:
            try:
                sub_episode = rename_engine.parse_episode(subtitle.name, episode_pattern)
            except rename_engine.RenameError:
                sub_episode = None
            if sub_episode is not None:
                same_episode = [
                    (scanned, plan)
                    for scanned, plan in candidates
                    if plan.absolute_episode == sub_episode
                ]
                if same_episode:
                    scanned, plan = max(
                        same_episode,
                        key=lambda item: _common_prefix_length(sub_stem, _stem(item[0].name)),
                    )
                    matched = (scanned, plan, detect_lang_tag(sub_stem) or "")

        if matched is None:
            unmatched.append(subtitle)
            continue

        video, video_plan, tag = matched
        target_name = build_target_name(video_plan.output_name, tag, subtitle.ext)
        if target_name.lower() in used_targets:
            unmatched.append(subtitle)
            continue
        used_targets.add(target_name.lower())
        plans.append(
            SubtitlePlan(
                subtitle=subtitle,
                video=video,
                plan=rename_engine.RenamePlan(
                    source_name=subtitle.name,
                    ext=subtitle.ext,
                    absolute_episode=video_plan.absolute_episode,
                    season=video_plan.season,
                    episode=video_plan.episode,
                    output_name=target_name,
                ),
                tag=tag,
                target_name=target_name,
            )
        )
    return plans, unmatched
