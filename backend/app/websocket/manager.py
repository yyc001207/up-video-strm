"""WebSocket 连接管理：按执行 ID 分组广播实时日志。

设计参考《设计规范文档》§4.11：``ConnectionManager`` 维护
``execution_id -> [WebSocket]``，``broadcast`` 对单条连接发送失败时静默摘除，
避免单个断连客户端阻塞日志推送。

阶段⓿-8：键类型放宽为 ``int | str``（自动化模块使用 ``automation:{task_id}``
字符串键），内部统一归一化为 ``str``，路由边界无需关心类型。
"""

from typing import Dict, List, Union

from fastapi import WebSocket

from app.core.logger import logger

ConnectionKey = Union[int, str]


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    @staticmethod
    def _key(execution_id: ConnectionKey) -> str:
        return str(execution_id)

    async def connect(self, execution_id: ConnectionKey, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(self._key(execution_id), []).append(websocket)

    def disconnect(self, execution_id: ConnectionKey, websocket: WebSocket) -> None:
        key = self._key(execution_id)
        conns = self.active_connections.get(key)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                self.active_connections.pop(key, None)

    async def broadcast(self, execution_id: ConnectionKey, message: dict) -> None:
        conns = self.active_connections.get(self._key(execution_id))
        for conn in list(conns or []):
            try:
                await conn.send_json(message)
            except Exception:
                self.disconnect(execution_id, conn)

    async def send_recent(self, execution_id: ConnectionKey, websocket: WebSocket, messages: list) -> None:
        for message in messages:
            try:
                await websocket.send_json(message)
            except Exception:
                break

    def has_connections(self, execution_id: ConnectionKey) -> bool:
        return bool(self.active_connections.get(self._key(execution_id)))


ws_manager = ConnectionManager()
