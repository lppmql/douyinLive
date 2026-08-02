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
from app.services.collector.stream_health import probe_stream_url


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

            # ── 3. 新地址必须先通过真实拉流验证 ──
            # 页面 DOM 可能仍残留已经失效的直播 FLV。没有验证就标记 active，
            # Worker 会在同一个坏地址上重复消耗全部分片重试次数。
            candidate_source = (
                db.query(StreamSource)
                .filter(
                    StreamSource.session_id == session_id,
                    StreamSource.status == "pending",
                )
                .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
                .first()
            )
            if not candidate_source:
                return {
                    "success": False,
                    "stream_url": None,
                    "error": "页面提取到了媒体地址，但没有保存待验证的流来源",
                    "source": None,
                }
            headers = dict(candidate_source.headers_json or {})
            health = await probe_stream_url(new_url, headers, probe_seconds=2.0)
            if not health["alive"]:
                candidate_source.status = "error"
                db.commit()
                return {
                    "success": False,
                    "stream_url": None,
                    "error": (
                        "页面提取到了媒体地址，但真实拉流验证失败："
                        f"{health.get('error') or '未知错误'}。"
                        "直播回放可能尚未生成或已经过期"
                    ),
                    "source": None,
                }

            # ── 4. 验证通过后原子切换 active 并更新场次 ──
            db.query(StreamSource).filter(
                StreamSource.session_id == session_id,
                StreamSource.status == "active",
            ).update({StreamSource.status: "expired"}, synchronize_session=False)
            candidate_source.status = "active"
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
