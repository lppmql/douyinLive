"""
历史场次同步和补齐 — 从 manual_collect.py 提取

负责：账号历史直播列表同步、历史场次详情补齐（大屏指标+评论+回放）
"""
import asyncio
import json
from typing import Callable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from playwright.async_api import BrowserContext
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.status import TaskStatus
from app.models.comments import Comment
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.scraper_accounts import ScraperAccount
from app.models.scraper_logs import ScraperLog
from app.models.stream_sources import StreamSource
from app.services.collector.browser import browser_manager
from app.services.collector.comments import _replace_session_comments, _save_comments
from app.services.collector.metrics import _apply_overview_to_session, _save_profiles, _save_stream_source, _save_trend_metrics
from app.services.collector.room import _scrape_history_session_detail
from app.services.collector.session import _apply_session_anchor_profile, _needs_history_enrichment
from app.services.collector.utils import (
    _extract_room_id_from_dashboard_url,
    _is_context_closed_message,
    _load_storage_cookies,
    _parse_dt,
    _safe_int,
)
from app.services.collector.constants import LIVE_SCREEN_URL

# 历史场次接口地址
HISTORY_API_URL = "https://leads.cluerich.com/live_console/history"
HISTORY_DETAIL_TIMEOUT_SECONDS = 45
HISTORY_DETAIL_CONCURRENCY = 1
CONTEXT_RECOVERY_ATTEMPTS = 2


def _fetch_history_payload(req: Request) -> dict:
    """在线程中执行平台历史接口请求，避免阻塞 FastAPI 事件循环。"""
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _sync_history_sessions(db: Session, account: ScraperAccount, room: LiveRoom) -> int:
    """同步当前账号下的历史直播场次到 live_sessions。"""
    storage_path = account.storage_state_path or ""
    cookie_jar = _load_storage_cookies(storage_path)
    if not cookie_jar:
        logger.warning("历史场次同步跳过：未找到可用 Cookie")
        return 0

    existing_sessions = {
        row.dashboard_url: row
        for row in db.query(LiveSession).filter(LiveSession.room_id == room.id).all()
        if row.dashboard_url
    }
    page_no = 1
    # 平台接口限制每页最多 20 条，超过会返回 code=3 且没有 live_history。
    limit = 20
    total = None
    synced = 0

    while total is None or (page_no - 1) * limit < total:
        query = urlencode({"total": 0, "limit": limit, "page": page_no})
        req = Request(
            f"{HISTORY_API_URL}?{query}",
            headers={
                "Cookie": "; ".join(f"{k}={v}" for k, v in cookie_jar.items()),
                "User-Agent": account.user_agent or "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            payload = await asyncio.to_thread(_fetch_history_payload, req)
        except Exception as exc:
            # 历史接口偶发断开时不能阻断企业主播映射和逐场详情采集。
            logger.warning("历史场次接口暂时不可用，继续企业场次同步: %s", exc)
            db.add(ScraperLog(level="warning", message=f"历史场次同步降级: {str(exc)[:500]}"))
            db.commit()
            return synced
        if (payload or {}).get("code") not in (0, None):
            message = (payload or {}).get("msg") or "历史场次接口返回错误"
            logger.warning("历史场次接口返回错误，继续企业主播同步: %s", message)
            db.add(ScraperLog(level="warning", message=f"历史场次同步降级: {message}"))
            db.commit()
            return synced

        data = (payload or {}).get("data", {}) or {}
        history_rows = data.get("live_history") or []
        total = _safe_int(data.get("total_count")) or 0

        if not history_rows:
            break

        logger.info(
            "历史场次分页采集: page=%s, page_size=%s, total=%s, synced_before=%s",
            page_no,
            len(history_rows),
            total,
            synced,
        )

        for item in history_rows:
            history_room_id = str(item.get("room_id") or "").strip()
            if not history_room_id:
                continue

            dashboard_url = f"{LIVE_SCREEN_URL}?room_id={history_room_id}&fullscreen=0"
            session = existing_sessions.get(dashboard_url)
            if session is None:
                session = LiveSession(room_id=room.id, dashboard_url=dashboard_url)
                db.add(session)
                existing_sessions[dashboard_url] = session
                synced += 1

            start_time = _parse_dt(item.get("start_time"))
            end_time = _parse_dt(item.get("end_time"))
            session.session_title = (
                session.session_title
                or (f"历史直播 {item.get('start_time')}" if item.get("start_time") else f"room_{history_room_id}")
            )
            session.stream_url = item.get("room_videorecord") or session.stream_url or None
            session.live_start_time = start_time or session.live_start_time
            session.live_end_time = end_time or session.live_end_time
            session.live_duration_seconds = _safe_int(item.get("live_time")) or session.live_duration_seconds or 0
            session.live_status = "ended" if end_time else (session.live_status or "finished")
            session.total_viewers = _safe_int(item.get("total_audience")) or session.total_viewers or 0
            avg_live_duration = _safe_int(item.get("avg_live_duration"))
            if avg_live_duration is not None:
                session.avg_watch_seconds = float(avg_live_duration)
            session.leads_count = _safe_int(item.get("live_leads_info_cnt")) or session.leads_count or 0
            session.private_message_count = _safe_int(item.get("consultation_count")) or session.private_message_count or 0

        page_no += 1
        # 大账号可能有数十页历史场次，主动让出执行权以保持进度和健康接口可响应。
        await asyncio.sleep(0)

    db.commit()
    return synced


def _order_history_enrichment_targets(pending_sessions: list[LiveSession]) -> list[LiveSession]:
    """返回本次要处理的全部待补场次，并优先覆盖从未尝试过的最新场次。"""
    return sorted(
        pending_sessions,
        key=lambda session: (
            session.detail_collection_status == TaskStatus.RETRYABLE,
            not bool(session.anchor_name),
            -(session.live_start_time.timestamp() if session.live_start_time else 0),
        ),
    )


async def _enrich_history_sessions(
    db: Session,
    context: BrowserContext,
    account: ScraperAccount,
    room: LiveRoom,
    progress_callback: Optional[Callable[[int, int, int, int], None]] = None,
    sanitize_error=None,
) -> dict:
    """尝试补齐全部历史场次的大屏详情、回放流和评论。"""
    del account
    current_context = context
    all_sessions = (
        db.query(LiveSession)
        .filter(
            LiveSession.room_id == room.id,
            LiveSession.live_start_time.isnot(None),
            LiveSession.live_end_time.isnot(None),
        )
        .order_by(LiveSession.live_start_time.desc())
        .all()
    )

    metric_session_ids = {row[0] for row in db.query(LiveMetric.session_id).distinct().all()}
    comment_session_ids = {row[0] for row in db.query(Comment.session_id).distinct().all()}
    profile_session_ids = {row[0] for row in db.query(LiveAudienceProfile.session_id).distinct().all()}
    stream_session_ids = {row[0] for row in db.query(StreamSource.session_id).distinct().all()}
    asset_session_ids = metric_session_ids | comment_session_ids | profile_session_ids | stream_session_ids
    pending_sessions = [
        session for session in all_sessions
        if _needs_history_enrichment(session, session.id in asset_session_ids)
    ]
    repaired_false_complete = 0
    for session in pending_sessions:
        if session.detail_collection_status == "complete":
            session.detail_collection_status = TaskStatus.RETRYABLE
            session.detail_collection_error = "此前未采到有效详情数据，已重新加入补齐队列"
            repaired_false_complete += 1
    if repaired_false_complete:
        db.commit()
        logger.warning("已修复 %s 场无数据但标记完整的历史场次", repaired_false_complete)
    # 全部待补场次都进入本次任务；单浏览器并发仍为 1，避免放开总量后挤爆电脑资源。
    target_sessions = _order_history_enrichment_targets(pending_sessions)
    enriched = 0
    checked = 0
    failed = 0
    semaphore = asyncio.Semaphore(HISTORY_DETAIL_CONCURRENCY)
    _sanitize = sanitize_error or (lambda v: str(v))

    async def scrape_one(session: LiveSession):
        nonlocal current_context
        room_id = _extract_room_id_from_dashboard_url(session.dashboard_url)
        if not room_id:
            return session, None, "缺少场次 room_id"
        async with semaphore:
            for attempt in range(CONTEXT_RECOVERY_ATTEMPTS + 1):
                try:
                    detail = await asyncio.wait_for(
                        _scrape_history_session_detail(current_context, room_id, session),
                        timeout=HISTORY_DETAIL_TIMEOUT_SECONDS,
                    )
                    detail_error = detail.get("error")
                    if not detail_error:
                        return session, detail, None
                    if not _is_context_closed_message(detail_error) or attempt >= CONTEXT_RECOVERY_ATTEMPTS:
                        return session, None, f"详情页采集失败: {_sanitize(detail_error)}"
                    browser_manager.invalidate_logged_in_context(current_context)
                    recovered_context, recovered, recovery_message = await browser_manager.get_logged_in_context()
                    if not recovered or not recovered_context:
                        return session, None, recovery_message or "浏览器上下文恢复失败，请重新扫码登录"
                    current_context = recovered_context
                except asyncio.TimeoutError:
                    return session, None, "详情页采集超时，可在下次采集重试"
                except Exception as exc:
                    compact_error = _sanitize(exc)
                    if not _is_context_closed_message(exc) or attempt >= CONTEXT_RECOVERY_ATTEMPTS:
                        return session, None, f"详情页采集失败: {compact_error}"
                    browser_manager.invalidate_logged_in_context(current_context)
                    recovered_context, recovered, recovery_message = await browser_manager.get_logged_in_context()
                    if not recovered or not recovered_context:
                        return session, None, recovery_message or "浏览器上下文恢复失败，请重新扫码登录"
                    current_context = recovered_context
            return session, None, "详情页采集失败，自动恢复次数已用完"

    detail_tasks = [asyncio.create_task(scrape_one(session)) for session in target_sessions]
    for detail_task in asyncio.as_completed(detail_tasks):
        session, detail, error = await detail_task
        checked += 1
        if error:
            failed += 1
            session.detail_collection_status = TaskStatus.RETRYABLE
            session.detail_collection_error = error
            db.commit()
            logger.warning("历史场次详情采集失败: session_id=%s error=%s", session.id, error)
            if progress_callback:
                progress_callback(checked, len(target_sessions), enriched, failed)
            continue

        if detail.get("validation_failed"):
            session.detail_collection_status = "unavailable"
            session.detail_collection_error = "平台详情页未回显该场次时间，无法安全确认主播归属"
            db.commit()
            failed += 1
            if progress_callback:
                progress_callback(checked, len(target_sessions), enriched, failed)
            continue

        overview = detail.get("overview", {})
        trend_rows = detail.get("trend", [])
        replay_url = detail.get("replay_url")
        comments_data = detail.get("comments", [])
        profiles = detail.get("profiles", [])
        anchor_profile = detail.get("anchor_profile", {}) or {}

        has_detail_data = bool(
            (overview.get("metrics", {}) if isinstance(overview, dict) else {})
            or trend_rows
            or comments_data
            or profiles
            or replay_url
        )
        if not has_detail_data:
            if not session.anchor_name:
                session.detail_collection_status = "unavailable"
                session.detail_collection_error = "平台未提供主播映射且详情接口为空，无法安全补齐"
            else:
                session.detail_collection_status = TaskStatus.RETRYABLE
                session.detail_collection_error = "平台详情接口本次返回空数据，将在下次刷新时重试"
            db.commit()
            failed += 1
            if progress_callback:
                progress_callback(checked, len(target_sessions), enriched, failed)
            continue

        session.detail_collection_status = "complete"
        session.detail_collection_error = None

        changed = _apply_session_anchor_profile(session, anchor_profile)
        changed = _apply_overview_to_session(session, overview) or changed
        if replay_url and session.stream_url != replay_url:
            session.stream_url = replay_url[:2000]
            changed = True
        if replay_url:
            _save_stream_source(db, session.id, replay_url)

        metrics_count = _save_trend_metrics(db, session.id, trend_rows)
        comments_count = (
            _replace_session_comments(db, session.id, comments_data)
            if detail.get("comments_authoritative")
            else _save_comments(db, session.id, comments_data)
        )
        if detail.get("comments_authoritative"):
            session.comments_count = comments_count
            changed = True
        elif comments_count:
            session.comments_count = max(session.comments_count or 0, comments_count)
            changed = True

        if profiles:
            db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == session.id).delete()
            _save_profiles(db, session.id, profiles)

        if changed or metrics_count or comments_count:
            db.commit()
        enriched += 1
        if progress_callback:
            progress_callback(checked, len(target_sessions), enriched, failed)
        logger.info(
            "历史场次详情补齐: session_id=%s, anchor=%s, metrics=%s, comments=%s, stream=%s",
            session.id,
            session.anchor_name or "未知主播",
            metrics_count,
            comments_count,
            bool(session.stream_url),
        )

    remaining = sum(
        session.detail_collection_status in (None, "", "pending", TaskStatus.RETRYABLE)
        for session in target_sessions
    )
    progress = {
        "enriched_count": enriched,
        "checked_count": checked,
        "remaining_count": remaining,
        "batch_size": len(target_sessions),
        "failed_count": failed,
        "concurrency": HISTORY_DETAIL_CONCURRENCY,
    }
    db.add(
        ScraperLog(
            level="info",
            message=(
                f"历史详情刷新完成: 检查={checked}, 补齐={enriched}, "
                f"失败={failed}"
            ),
            raw_json=progress,
        )
    )
    db.commit()
    return progress


async def collect_live_session_snapshot(
    db: Session,
    context: BrowserContext,
    session: LiveSession,
) -> dict:
    """按刷新采集的完整结构更新一场正在直播的场次。"""
    room_id = _extract_room_id_from_dashboard_url(session.dashboard_url)
    if not room_id:
        raise RuntimeError("直播场次缺少 room_id，无法采集完整数据")

    detail = await _scrape_history_session_detail(
        context,
        room_id,
        session,
        validate_history=False,
    )
    if detail.get("error"):
        raise RuntimeError(f"实时完整快照页面采集失败: {detail['error']}")
    overview = detail.get("overview", {})
    trend_rows = detail.get("trend", [])
    comments_data = detail.get("comments", [])
    profiles = detail.get("profiles", [])
    anchor_profile = detail.get("anchor_profile", {}) or {}
    replay_url = detail.get("replay_url")

    changed = _apply_session_anchor_profile(session, anchor_profile)
    changed = _apply_overview_to_session(session, overview) or changed
    metrics_count = _save_trend_metrics(db, session.id, trend_rows)
    comments_count = (
        _replace_session_comments(db, session.id, comments_data)
        if detail.get("comments_authoritative")
        else _save_comments(db, session.id, comments_data)
    )
    profiles_count = 0
    if profiles:
        db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == session.id).delete()
        profiles_count = _save_profiles(db, session.id, profiles)
    if detail.get("comments_authoritative"):
        session.comments_count = comments_count
        changed = True
    elif comments_count:
        session.comments_count = max(session.comments_count or 0, comments_count)
        changed = True
    if replay_url and session.stream_url != replay_url:
        session.stream_url = replay_url[:2000]
        _save_stream_source(db, session.id, replay_url)
        changed = True
    if session.detail_collection_status != "complete" or session.detail_collection_error:
        session.detail_collection_status = "complete"
        session.detail_collection_error = None
        changed = True
    if changed:
        db.commit()

    result = {
        "overview_field_count": len((overview.get("metrics", {}) or {})),
        "trend_row_count": len(trend_rows),
        "new_metric_count": metrics_count,
        "new_comment_count": comments_count,
        "profile_count": profiles_count,
        "stream_saved": bool(replay_url),
        "anchor_profile_updated": bool(anchor_profile),
    }
    logger.info("实时完整快照采集完成: session=%s result=%s", session.id, result)
    return result
