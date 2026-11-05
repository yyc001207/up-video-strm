"""北京时间工具。

项目约定：所有对外展示/持久化的时间一律为北京时间（UTC+8），格式为
``YYYY-MM-DD HH:mm:ss`` 或 ``YYYY-MM-DD``；数据库列不带时区信息，因此这里统一
返回「北京时间墙钟时间」的 naive datetime，避免受部署机器本地时区影响。

注意：SQLite 的 ``CURRENT_TIMESTAMP`` / ``func.now()`` 返回的是 UTC，不能用于
创建/更新时间字段；模型统一使用本模块的 ``beijing_now`` 作为默认值。
"""

from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def beijing_now() -> datetime:
    """返回当前北京时间（naive，不带时区信息）。"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def to_beijing(value: datetime) -> datetime:
    """把带时区的 datetime 转为北京时间 naive；naive 视为已是北京时间。"""
    if value.tzinfo is None:
        return value
    return value.astimezone(BEIJING_TZ).replace(tzinfo=None)
