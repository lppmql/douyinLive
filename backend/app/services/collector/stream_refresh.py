"""
流地址自动刷新服务

当 m3u8 过期时，自动用已保存的 Cookie 打开抖音大屏页面，
重新抓取新的流地址，全程无需人工操作。

用法:
    from app.services.collector.stream_refresh import refresh_session_stream_url

    result = await refresh_session_stream_url(db, session_id)
    # → {"success": True, "stream_url": "https://...", "error": None}
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource


async def refresh_session_stream_url(
    db: Session,
    session_id: int,
) -> dict:
    """
    自动刷新场次流地址。

    步骤：
    1. 查找场次的 dashboard_url
    2. 获取已登录的浏览器上下文（复用 Cookie）
    3. 从大屏页面抓取新的 m3u8 地址
    4. 更新 LiveSession.stream_url

    Returns:
        {
            "success": bool,
            "stream_url": str | None,    # 成功时返回新的流地址
            "error": str | None,          # 失败时返回原因
            "source": str | None,         # "fresh"（新采集） / "existing"（复用已有）/ None（失败）
        }
    """
    session = db.get(LiveSession, session_id)
    if not session:
        return {
            "success": False,
            "stream_url": None,
            "error": f"直播场次不存在: session_id={session_id}",
            "source": None,
        }

    dashboard_url = session.dashboard_url
    if not dashboard_url:
        return {
            "success": False,
            "stream_url": None,
            "error": "该场次缺少大屏页面地址（dashboard_url），无法自动刷新流地址",
            "source": None,
        }

    # ── 1. 获取浏览器登录上下文 ──
    from app.services.collector.browser import browser_manager

    try:
        async with browser_manager.session_lease(
            f"stream-refresh:{session_id}", kind="refresh"
        ):
            context, is_valid, message = await browser_manager.get_logged_in_context()
            if not is_valid or not context:
                return {
                    "success": False,
                    "stream_url": None,
                    "error": f"Cookie 登录态不可用，请重新扫码登录: {message}",
                    "source": None,
                }

            # ── 2. 从大屏页面抓取新流地址 ──
            from app.services.collector.stream_collector import StreamCollector

            logger.info(
                "正在为场次 %s 自动刷新流地址（dashboard: %s）...",
                session_id,
                dashboard_url[:80],
            )

            new_url = await StreamCollector(db, context).fetch_stream_url(
                dashboard_url, session_id
            )

            if not new_url:
                return {
                    "success": False,
                    "stream_url": None,
                    "error": (
                        "无法从大屏页面提取流地址，可能直播已结束且回放已过期，"
                        "或者页面结构发生了变化"
                    ),
                    "source": None,
                }

            # ── 3. 更新 LiveSession.stream_url ──
            session.stream_url = new_url[:2000]
            db.commit()

            logger.info(
                "场次 %s 流地址自动刷新成功: %s...",
                session_id,
                new_url[:80],
            )

            return {
                "success": True,
                "stream_url": new_url,
                "error": None,
                "source": "fresh",
            }

    except Exception as exc:
        logger.error("场次 %s 流地址自动刷新异常: %s", session_id, exc)
        return {
            "success": False,
            "stream_url": None,
            "error": f"自动刷新异常: {exc}",
            "source": None,
        }


def get_best_available_stream_url(
    db: Session,
    session_id: int,
) -> tuple[Optional[str], Optional[dict], str]:
    """
    获取场次当前最佳可用流地址（不做刷新，只读取现有数据）。

    Returns:
        (stream_url, headers_dict, source_type)
        source_type: "stream_source_active" | "stream_source_any" | "session_fallback" | "none"
    """
    # 优先：status=active 的 StreamSource
    source = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id, StreamSource.status == "active")
        .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .first()
    )
    if source and source.m3u8_url:
        headers = dict(source.headers_json) if source.headers_json else {}
        return source.m3u8_url, headers, "stream_source_active"

    # 次选：任意 StreamSource（即使标记为 expired）
    source = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id)
        .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .first()
    )
    if source and source.m3u8_url:
        headers = dict(source.headers_json) if source.headers_json else {}
        return source.m3u8_url, headers, "stream_source_any"

    # 兜底：LiveSession.stream_url
    session = db.get(LiveSession, session_id)
    if session and session.stream_url:
        return session.stream_url, {}, "session_fallback"

    return None, {}, "none"
