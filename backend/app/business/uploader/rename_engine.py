"""上传管理：文件名解析与重命名。

约定（见 ``docs/design/upload-module-plan.md`` §6.2）：

- 季数由任务配置指定，不从文件名推断；
- 从文件名解析**绝对集号**（``S01E13`` 的 ``S01`` 不参与季号）；
- 输出季内集号 ``= 绝对集号 - 源起始集号 + 1``，例如输出季数 2、源起始集号 13 时，
  源文件第 13 集输出为 ``S02E01``；
- 输出文件名由模板渲染，默认 ``S{season:02}E{episode:02}.{ext}``；
- 集数默认由内置正则解析；规则可配置 ``episode_pattern`` 覆盖默认解析（见
  [重命名规则模型](../../core/models/uploader/rename_rule.py)）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_TEMPLATE = "S{season:02}E{episode:02}.{ext}"
"""默认文件名模板。"""

_MAX_SEASON = 99
_MAX_EPISODE = 9999

# 集数解析：按顺序匹配，命中即取第一组数字；未命中时回退到「独立的最后一个数字」。
# 说明：`EPxx` / `SxxExx` 均要求前面不是字母数字，避免把哈希串（如 `[5AAEB1E9]`）里的
# `E9` 误识别成第 9 集；裸集数要求前后不是字母数字，避免把 `1920x1080` 等分辨率当集数。
_EPISODE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"第\s*(\d{1,4})\s*[集话話]"), "第N集"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])[Ss]\d{1,3}\s*[Ee][Pp]?\s*(\d{1,4})(?![0-9])"), "SxxExx"),
    (re.compile(r"(?i)(?<![A-Za-z0-9])[Ee][Pp]\s*[-_ ]?(\d{1,4})(?![0-9])"), "EPxx"),
    (re.compile(r"[\[【(]\s*(\d{1,4})\s*[\]】)]"), "[xx]"),
    (re.compile(r"(?<![A-Za-z0-9])(\d{1,4})(?=\s*[-_.\s]|$)"), "xx"),
)

# 末位回退：只认前后都不是字母数字的独立数字（避免哈希串、分辨率等噪声）。
_STANDALONE_DIGITS = re.compile(r"(?<![A-Za-z0-9])(\d{1,4})(?![A-Za-z0-9])")

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')
_ILLEGAL_CHARS = _INVALID_FILENAME_CHARS

# 输出文件名必须是 SxxExx.ext 形式（季/集各至少两位）
_OUTPUT_NAME_RE = re.compile(r"^S(\d{2,3})E(\d{2,4})\.([A-Za-z0-9]+)$")


class RenameError(ValueError):
    """文件无法按规则重命名（无集数、模板非法、扩展名缺失等）。"""


@dataclass(frozen=True)
class RenamePlan:
    """单个源文件的重命名结果。"""

    source_name: str
    ext: str
    absolute_episode: int
    season: int
    episode: int
    output_name: str


def parse_extension(filename: str) -> str:
    """取扩展名（小写、不含点），无扩展名时抛 RenameError。"""
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in name:
        raise RenameError("文件名缺少扩展名")
    ext = name.rsplit(".", 1)[-1].strip().lower()
    if not ext or not re.fullmatch(r"[A-Za-z0-9]+", ext):
        raise RenameError("扩展名不合法")
    return ext


def validate_episode_pattern(pattern: str | None) -> str | None:
    """校验用户自定义的集数提取正则；空字符串返回 None（使用默认规则）。

    自定义正则必须合法且至少包含一个分组（取第 1 个分组作为集数），
    例如 ``r"-\\s*(\\d{1,4})\\s*\\("``。
    """
    if pattern is None:
        return None
    candidate = pattern.strip()
    if not candidate:
        return None
    if len(candidate) > 256:
        raise RenameError("集数提取正则过长（最多 256 个字符）")
    try:
        compiled = re.compile(candidate)
    except re.error as exc:
        raise RenameError(f"集数提取正则不合法：{exc}") from exc
    if compiled.groups < 1:
        raise RenameError("集数提取正则至少需要一个分组，例如 (\\d+)")
    return candidate


def _parse_episode_with_pattern(stem: str, pattern: str) -> int | None:
    """用自定义正则解析集号：取第 1 个分组，必须为纯数字且在合法范围内。"""
    match = re.compile(pattern).search(stem)
    if match is None:
        return None
    raw = match.group(1)
    if raw is None or not raw.isdigit():
        return None
    value = int(raw)
    if 0 < value <= _MAX_EPISODE:
        return value
    return None


def parse_episode(filename: str, pattern: str | None = None) -> int | None:
    """从文件名解析绝对集号；无法解析返回 None。

    ``pattern`` 不为空时只使用该自定义正则（第 1 个分组），不再回退默认规则。
    """
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if pattern:
        return _parse_episode_with_pattern(stem, pattern)
    for regex, _label in _EPISODE_PATTERNS:
        matches = regex.findall(stem)
        if matches:
            value = int(matches[-1])
            if 0 < value <= _MAX_EPISODE:
                return value
    digits = _STANDALONE_DIGITS.findall(stem)
    if digits:
        value = int(digits[-1])
        if 0 < value <= _MAX_EPISODE:
            return value
    return None


def sanitize_filename(name: str) -> str:
    """清理 Windows 非法字符与首尾空白。"""
    return _INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")


def validate_template(template: str) -> str:
    """校验模板并返回规范化后的模板。

    模板必须包含 ``{season}`` / ``{episode}`` / ``{ext}``，渲染结果必须满足
    ``SxxExx.ext``（例如 ``S01E03.mp4``）。
    """
    candidate = (template or "").strip() or DEFAULT_TEMPLATE
    for key in ("season", "episode", "ext"):
        if "{" + key not in candidate:
            raise RenameError(f"模板缺少变量 {key}")
    try:
        rendered = _render(candidate, season=1, episode=3, ext="mp4")
    except (KeyError, IndexError, ValueError) as exc:
        raise RenameError(f"模板变量不合法：{exc}") from exc
    if not _OUTPUT_NAME_RE.match(rendered):
        raise RenameError("模板渲染结果必须为 SxxExx.ext（例如 S01E03.mp4）")
    return candidate


def _render(template: str, *, season: int, episode: int, ext: str) -> str:
    """渲染模板：支持 ``{season}`` / ``{episode}`` / ``{ext}`` 与 ``:02`` 补零。"""
    try:
        rendered = template.format(season=season, episode=episode, ext=ext)
    except (KeyError, IndexError, ValueError) as exc:
        raise RenameError(f"模板渲染失败：{exc}") from exc
    return sanitize_filename(rendered)


def validate_season_episode(season: int, start_episode: int) -> tuple[int, int]:
    """校验季数与源起始集号范围。"""
    if season < 1 or season > _MAX_SEASON:
        raise RenameError(f"季数必须在 1-{_MAX_SEASON} 之间")
    if start_episode < 1 or start_episode > _MAX_EPISODE:
        raise RenameError(f"源起始集号必须在 1-{_MAX_EPISODE} 之间")
    return season, start_episode


def plan_rename(
    filename: str,
    *,
    season: int,
    start_episode: int = 1,
    template: str = DEFAULT_TEMPLATE,
    episode_pattern: str | None = None,
) -> RenamePlan:
    """为单个源文件生成重命名计划；集号越界或无集数时抛 RenameError。"""
    season, start_episode = validate_season_episode(season, start_episode)
    template = validate_template(template)
    episode_pattern = validate_episode_pattern(episode_pattern)
    ext = parse_extension(filename)
    absolute = parse_episode(filename, episode_pattern)
    if absolute is None:
        raise RenameError("文件名中未解析到集数，无法重命名")
    episode = absolute - start_episode + 1
    if episode < 1:
        raise RenameError(
            f"第 {absolute} 集早于源起始集号 {start_episode}，无法映射到输出季 {season}"
        )
    output_name = _render(template, season=season, episode=episode, ext=ext)
    if not _OUTPUT_NAME_RE.match(output_name):
        raise RenameError("重命名结果不是 SxxExx.ext 形式")
    return RenamePlan(
        source_name=filename,
        ext=ext,
        absolute_episode=absolute,
        season=season,
        episode=episode,
        output_name=output_name,
    )
