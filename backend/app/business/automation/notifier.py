"""自动化任务：异常终止通知（阶段③）。

按计划「异常终止通知托盘 + 网页红点」：
- 托盘：调用桌面壳注入的通知器（``app.desktop.notify``），非桌面环境静默跳过；
- 网页红点：向 ``automation:{task_id}`` 频道推 ``alert`` 帧，前端据此点亮运行指示。

用户主动停止不调用本模块，因此不会产生通知。
"""

from __future__ import annotations

from app.business.automation.execution_logger import channel
from app.core.logger import logger


def _desktop_notify(task_name: str, message: str) -> bool:
    try:
        from app.desktop import notify

        return bool(notify("自动化任务异常", f"{task_name}：{message}"))
    except Exception:  # pragma: no cover - 非桌面环境
        return False


async def notify_abnormal(task_id: int, task_name: str, message: str) -> bool:
    """异常终止通知：写日志、推 WS 红点、尝试托盘通知；返回托盘是否成功。"""
    logger.warning("自动化任务异常（%s）：%s", task_name, message)
    try:
        from app.websocket.manager import ws_manager

        await ws_manager.broadcast(
            channel(task_id),
            {"type": "alert", "status": "fail", "message": message, "task_id": task_id},
        )
    except Exception:  # pragma: no cover
        pass
    return _desktop_notify(task_name, message)
