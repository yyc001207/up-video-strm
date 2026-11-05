"""自动化任务运行实例表与进程内互斥（阶段② 提供基础能力，引擎在阶段③使用）。

- ``RUNNING``：``{automation_task_id: asyncio.Task}``，同一任务仅一个运行实例；
- ``STOP_EVENTS``：每个运行实例的停止事件；
- ``LOCKS``：按 ``(kind, id)`` 的 FIFO 锁，用于 C 内部对 A/B 启动的串行化。

本表仅进程内有效：应用退出即全部失效，重启后不自动恢复运行。
"""

from __future__ import annotations

import asyncio

RUNNING: dict[int, asyncio.Task] = {}
STOP_EVENTS: dict[int, asyncio.Event] = {}
_LOCKS: dict[tuple[str, int], asyncio.Lock] = {}


def is_running(task_id: int) -> bool:
    """任务是否已有运行实例（已结束但未注销的实例视为未运行）。"""
    task = RUNNING.get(task_id)
    return task is not None and not task.done()


def register(task_id: int, task: asyncio.Task) -> None:
    RUNNING[task_id] = task
    STOP_EVENTS[task_id] = asyncio.Event()


def unregister(task_id: int) -> None:
    RUNNING.pop(task_id, None)
    STOP_EVENTS.pop(task_id, None)


def request_stop(task_id: int) -> bool:
    """请求停止运行中的任务；无运行实例时返回 False。"""
    event = STOP_EVENTS.get(task_id)
    if event is None:
        return False
    event.set()
    return True


def stop_requested(task_id: int) -> bool:
    event = STOP_EVENTS.get(task_id)
    return bool(event and event.is_set())


def get_stop_event(task_id: int) -> asyncio.Event:
    return STOP_EVENTS.setdefault(task_id, asyncio.Event())


def lock_for(kind: str, target_id: int) -> asyncio.Lock:
    """获取 ``(kind, id)`` 对应的 FIFO 锁（asyncio.Lock 按等待顺序唤醒）。"""
    key = (kind, target_id)
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def clear() -> None:
    """测试辅助：清空全部进程内状态。"""
    RUNNING.clear()
    STOP_EVENTS.clear()
    _LOCKS.clear()
