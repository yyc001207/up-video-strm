"""跨模块活跃执行注册表（自动化模块前置改动 ⓿-3）。

用途：任务调度（``openlist``）与上传管理（``uploader``）的 ``start_execution``
在**入队前**登记活跃执行，引擎 ``finally`` 时注销；自动化模块据此判断绑定任务
是否正被占用（手动执行与自动化执行同受约束，冲突返回 400「任务正在执行」）。

约定：
- 键为 ``(模块, execution_id)``，值为关联的 ``task_id``（目录执行为 0）；
- 闸门只对 ``task_id > 0`` 生效：目录执行（A 的 task_id=0）互不排斥；
- 排队中的执行同样视为活跃（在引擎协程真正开始前就已登记）。
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

_KIND_OPENLIST = "openlist"
_KIND_UPLOAD = "upload"

# (kind, execution_id) -> task_id
_ACTIVE: Dict[Tuple[str, int], int] = {}


def try_register(kind: str, execution_id: int, task_id: int) -> bool:
    """登记活跃执行；若同模块同任务已有活跃执行则返回 False（闸门拒绝）。"""
    if task_id > 0:
        for (active_kind, _execution_id), active_task_id in _ACTIVE.items():
            if active_kind == kind and active_task_id == task_id:
                return False
    _ACTIVE[(kind, int(execution_id))] = int(task_id)
    return True


def release(kind: str, execution_id: int) -> None:
    """注销活跃执行（幂等）。"""
    _ACTIVE.pop((kind, int(execution_id)), None)


def clear(kind: Optional[str] = None) -> None:
    """清空注册表（kind 为空时清空全部；启动清理 / 测试用）。"""
    if kind is None:
        _ACTIVE.clear()
        return
    for key in [key for key in _ACTIVE if key[0] == kind]:
        _ACTIVE.pop(key, None)


def is_execution_active(kind: str, execution_id: int) -> bool:
    return (kind, int(execution_id)) in _ACTIVE


def is_task_active(kind: str, task_id: int) -> bool:
    """指定模块的某个任务是否已有活跃执行（task_id<=0 恒为 False）。"""
    if task_id <= 0:
        return False
    return any(
        active_kind == kind and active_task_id == task_id
        for (active_kind, _execution_id), active_task_id in _ACTIVE.items()
    )


def active_executions(kind: Optional[str] = None) -> Iterable[Tuple[str, int, int]]:
    """返回 ``(kind, execution_id, task_id)`` 的当前快照。"""
    for (active_kind, execution_id), task_id in list(_ACTIVE.items()):
        if kind is not None and active_kind != kind:
            continue
        yield active_kind, execution_id, task_id


OPENLIST = _KIND_OPENLIST
UPLOAD = _KIND_UPLOAD
