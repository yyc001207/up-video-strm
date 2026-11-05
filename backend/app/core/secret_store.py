"""敏感配置的本地加密存储。

Windows 上使用 DPAPI（``CryptProtectData`` / ``CryptUnprotectData``，绑定当前用户账户），
其它平台退化为 base64 混淆并显式标注 ``plain:`` 前缀。两种格式都能被
``decrypt_secret`` 正确读取，因此升级/迁移不会丢数据。

注意：DPAPI 密文绑定当前 Windows 用户，换用户或换机器后无法解密；
数据库属于本机应用数据目录，符合这一使用场景。
"""

from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes
from typing import Optional

DPAPI_PREFIX = "dpapi:"
PLAIN_PREFIX = "plain:"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_supported() -> bool:
    return sys.platform == "win32"


def _to_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, max(len(data), 1))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi_call(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _keep = _to_blob(data)
    out_blob = _DataBlob()
    func = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = func(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def encrypt_secret(plain: str) -> str:
    """加密明文；空串原样返回空串。"""
    if not plain:
        return ""
    raw = plain.encode("utf-8")
    if _dpapi_supported():
        try:
            return DPAPI_PREFIX + base64.b64encode(_dpapi_call(raw, protect=True)).decode("ascii")
        except OSError:
            pass
    return PLAIN_PREFIX + base64.b64encode(raw).decode("ascii")


def decrypt_secret(value: Optional[str]) -> str:
    """解密存储值；兼容历史明文（无前缀时原样返回）。"""
    if not value:
        return ""
    if value.startswith(DPAPI_PREFIX):
        encoded = base64.b64decode(value[len(DPAPI_PREFIX):].encode("ascii"))
        return _dpapi_call(encoded, protect=False).decode("utf-8", errors="replace")
    if value.startswith(PLAIN_PREFIX):
        return base64.b64decode(value[len(PLAIN_PREFIX):].encode("ascii")).decode("utf-8", errors="replace")
    return value


def mask_secret(secret: Optional[str], visible: int = 4) -> str:
    """脱敏展示：只保留末尾若干位，例如 ``****abcd``。"""
    if not secret:
        return ""
    if len(secret) <= visible:
        return "****"
    return "****" + secret[-visible:]
