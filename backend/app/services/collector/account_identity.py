"""从企业号后台读取当前扫码账号的真实身份信息。"""

from __future__ import annotations

from typing import Any

from playwright.async_api import BrowserContext

from app.core.logger import logger
from app.services.collector.constants import LEADS_BASE


USER_INFO_URL = f"{LEADS_BASE}/bff/user/info"


def parse_account_identity(payload: Any) -> dict[str, str | None]:
    """只读取已验证的账号字段，避免把主播或企业名称误当成扫码账号。"""
    if not isinstance(payload, dict) or payload.get("error_code") not in (None, 0):
        return {"douyin_nickname": None, "douyin_id": None}
    data = payload.get("data")
    if not isinstance(data, dict):
        return {"douyin_nickname": None, "douyin_id": None}

    nickname = str(data.get("nick_name") or "").strip() or None
    douyin_id = str(data.get("douyin_unique_id") or "").strip() or None
    return {"douyin_nickname": nickname, "douyin_id": douyin_id}


async def fetch_account_identity(context: BrowserContext) -> dict[str, str | None]:
    """复用浏览器上下文 Cookie 请求当前用户接口，不记录响应中的敏感信息。"""
    try:
        response = await context.request.get(USER_INFO_URL, timeout=15_000)
        if not response.ok:
            logger.warning("读取扫码账号信息失败 status=%s", response.status)
            return {"douyin_nickname": None, "douyin_id": None}
        return parse_account_identity(await response.json())
    except Exception as exc:
        logger.warning("读取扫码账号信息异常: %s", exc)
        return {"douyin_nickname": None, "douyin_id": None}
