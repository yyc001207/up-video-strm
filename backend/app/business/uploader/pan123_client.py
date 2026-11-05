"""123 云盘开放平台 API 封装（v1）。

所有 HTTP 调用集中在本模块，业务层不拼接 URL。官方文档：
https://www.123pan.com/developer

统一约定：
- 请求头 ``Platform: open``；鉴权后附带 ``Authorization: Bearer <accessToken>``；
- 响应 ``{"code": 0, "message": "...", "data": {...}}``，``code != 0`` 视为业务错误；
- 分片 PUT 使用预签名 URL，不携带 Authorization / Platform 头。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx

from app.core.exceptions import BadRequestException

DEFAULT_BASE_URL = "https://open-api.123pan.com"
DEFAULT_TIMEOUT = 20.0
MAX_LIST_PAGE_SIZE = 100
# 文件列表 type：0=文件，1=文件夹（官方文档字段）
REMOTE_TYPE_FILE = 0
REMOTE_TYPE_DIR = 1


def parse_expiry(raw: Any) -> Optional[datetime]:
    """解析 token 过期时间：支持 epoch 秒（int/数字字符串）与 ISO8601 字符串。"""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().isdigit()):
        timestamp = float(raw)
        return datetime.fromtimestamp(timestamp)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    return None


class Pan123Client:
    """123 云盘开放平台异步客户端。"""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "Pan123Client":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # ---------- 底层请求 ----------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> Any:
        headers = {"Platform": "open", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = await self._http.request(method, path, params=params, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise BadRequestException(f"123 云盘请求失败：{exc}") from exc
        if response.status_code == 429:
            raise BadRequestException("123 云盘接口限流（429），请稍后重试")
        try:
            payload = response.json()
        except ValueError as exc:
            raise BadRequestException(f"123 云盘返回非 JSON 数据（HTTP {response.status_code}）") from exc
        if not isinstance(payload, dict):
            raise BadRequestException("123 云盘返回数据结构异常")
        if response.status_code in (401, 403):
            raise BadRequestException(f"123 云盘鉴权失败：{payload.get('message') or '凭据无效'}")
        if response.status_code >= 400:
            raise BadRequestException(
                f"123 云盘接口错误（HTTP {response.status_code}）：{payload.get('message') or '请求失败'}"
            )
        code = payload.get("code")
        if code not in (0, 200):
            raise BadRequestException(f"123 云盘接口错误：{payload.get('message') or code}")
        return payload.get("data")

    # ---------- 鉴权 ----------

    async def get_access_token(self) -> tuple[str, Optional[datetime]]:
        """用 clientID / clientSecret 换取 access_token。"""
        data = await self._request(
            "POST",
            "/api/v1/access_token",
            json={"clientID": self.client_id, "clientSecret": self.client_secret},
        )
        token = (data or {}).get("accessToken")
        if not token:
            raise BadRequestException("123 云盘未返回 access_token")
        return str(token), parse_expiry((data or {}).get("expiredAt"))

    async def test_connection(self) -> str:
        """换取 token 并读取根目录第一页，验证凭据与网络。"""
        token, _ = await self.get_access_token()
        await self.list_files(token, parent_file_id=0, page=1, limit=1)
        return "连接成功"

    # ---------- 文件列表 ----------

    async def list_files(
        self,
        token: str,
        *,
        parent_file_id: int = 0,
        page: int = 1,
        limit: int = MAX_LIST_PAGE_SIZE,
    ) -> tuple[list[dict], int]:
        data = await self._request(
            "GET",
            "/api/v1/file/list",
            token=token,
            params={
                "parentFileId": parent_file_id,
                "page": page,
                "limit": limit,
                "orderBy": "file_name",
                "orderDirection": "asc",
                "trashed": "false",
            },
        )
        file_list = list((data or {}).get("fileList") or [])
        total = int((data or {}).get("total") or len(file_list))
        return file_list, total

    async def list_all_files(self, token: str, parent_file_id: int = 0) -> list[dict]:
        """分页取出某个目录下的全部文件/子目录。"""
        files: list[dict] = []
        page = 1
        while True:
            batch, total = await self.list_files(token, parent_file_id=parent_file_id, page=page)
            files.extend(batch)
            if not batch or len(files) >= total:
                return files
            page += 1

    async def find_file(self, token: str, filename: str, parent_file_id: int = 0) -> Optional[dict]:
        """按文件名精确查找（区分大小写，以服务端返回为准）。"""
        for item in await self.list_all_files(token, parent_file_id):
            if item.get("filename") == filename:
                return item
        return None

    async def resolve_dir_path(self, token: str, remote_dir: str) -> int:
        """把 ``/a/b`` 形式的云端目录解析为 parentFileId。

        一期不自动创建目录：路径中任一层不存在直接报错，提示用户手工创建。
        """
        parts = [part for part in (remote_dir or "").strip().strip("/").split("/") if part]
        if not parts:
            return 0
        current_id = 0
        walked: list[str] = []
        for part in parts:
            walked.append(part)
            found = None
            for item in await self.list_all_files(token, current_id):
                if item.get("type") == REMOTE_TYPE_DIR and item.get("filename") == part:
                    found = item
                    break
            if found is None:
                raise BadRequestException(f"123 云盘目录不存在：/{'/'.join(walked)}，请先在网盘手工创建")
            current_id = int(found["fileId"])
        return current_id

    # ---------- 上传 ----------

    async def create_file(
        self,
        token: str,
        *,
        parent_file_id: int,
        filename: str,
        etag: str,
        size: int,
        duplicate: int = 1,
    ) -> dict:
        """预上传：返回 ``reuse=True`` 即秒传完成，否则含 ``preuploadID`` / ``sliceSize``。"""
        data = await self._request(
            "POST",
            "/api/v1/upload/create_file",
            token=token,
            json={
                "parentFileId": parent_file_id,
                "filename": filename,
                "etag": etag,
                "size": size,
                "duplicate": duplicate,
            },
        )
        return data or {}

    async def get_upload_url(self, token: str, preupload_id: str, slice_no: int) -> str:
        data = await self._request(
            "POST",
            "/api/v1/upload/get_upload_url",
            token=token,
            json={"preuploadID": preupload_id, "sliceNo": slice_no},
        )
        url = (data or {}).get("presignedURL")
        if not url:
            raise BadRequestException("123 云盘未返回分片上传地址")
        return str(url)

    async def upload_part(self, presigned_url: str, content: bytes) -> None:
        """PUT 上传单个分片（预签名 URL，不带鉴权头）。"""
        try:
            response = await self._http.put(presigned_url, content=content)
        except httpx.HTTPError as exc:
            raise BadRequestException(f"分片上传失败：{exc}") from exc
        if response.status_code >= 300:
            raise BadRequestException(f"分片上传失败（HTTP {response.status_code}）")

    async def list_upload_parts(self, token: str, preupload_id: str) -> list[dict]:
        data = await self._request(
            "GET",
            "/api/v1/upload/list_upload_parts",
            token=token,
            params={"preuploadID": preupload_id},
        )
        return list((data or {}).get("parts") or [])

    async def upload_complete(self, token: str, preupload_id: str) -> dict:
        data = await self._request(
            "POST",
            "/api/v1/upload/complete",
            token=token,
            json={"preuploadID": preupload_id},
        )
        return data or {}

    async def upload_async_result(self, token: str, preupload_id: str) -> dict:
        data = await self._request(
            "POST",
            "/api/v1/upload/upload_async_result",
            token=token,
            json={"preuploadID": preupload_id},
        )
        return data or {}

    async def delete_files(self, token: str, file_ids: list[int]) -> None:
        await self._request("POST", "/api/v1/file/delete", token=token, json={"fileIDs": file_ids})
