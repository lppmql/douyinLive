"""
场次管理 — 从 manual_collect.py 提取

负责：场次创建/更新、重复场次合并修复、主播资料写入、补齐判断
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.core.status import TaskStatus
from app.models.comments import Comment
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.scraper_logs import ScraperLog
from app.models.stream_sources import StreamSource
from app.services.collector.utils import (
    _comment_belongs_to_session,
    _comment_identity,
    _parse_dt,
    _safe_int,
)

# 大屏页地址（与 manual_collect 共享常量）
LIVE_SCREEN_URL = "https://leads.cluerich.com/pc/analysis/live-screen"


def _get_or_create_session(
    db: Session,
    room: LiveRoom,
    platform_room_id: str,
    session_title: str,
    is_live: bool,
    now: datetime,
) -> LiveSession:
    """严格按平台 roomId 获取场次，禁止把入口评论写入数据库最新场次。"""
    dashboard_url = f"{LIVE_SCREEN_URL}?room_id={platform_room_id}&fullscreen=0"
    session = (
        db.query(LiveSession)
        .filter(
            LiveSession.room_id == room.id,
            LiveSession.dashboard_url == dashboard_url,
        )
        .order_by(LiveSession.id.asc())
        .first()
    )

    if not session:
        session = LiveSession(
            room_id=room.id,
            dashboard_url=dashboard_url,
            session_title=session_title,
            live_status="live" if is_live else "scheduled",
            live_start_time=now if is_live else None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    return session


def _upsert_history_session(
    db: Session,
    room: LiveRoom,
    item: dict,
) -> bool:
    """把历史直播列表中的一条记录同步到 LiveSession。"""
    history_room_id = str(item.get("room_id") or "").strip()
    if not history_room_id:
        return False

    dashboard_url = f"{LIVE_SCREEN_URL}?room_id={history_room_id}&fullscreen=0"
    session = (
        db.query(LiveSession)
        .filter(
            LiveSession.room_id == room.id,
            LiveSession.dashboard_url == dashboard_url,
        )
        .first()
    )

    created = session is None
    if session is None:
        session = LiveSession(room_id=room.id, dashboard_url=dashboard_url)
        db.add(session)

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

    db.commit()
    return created


def _apply_session_anchor_profile(session: LiveSession, profile: dict) -> bool:
    """保存小眼睛展开后的本场主播资料，避免不同主播历史场次串号。"""
    changed = False
    for field in ("anchor_name", "anchor_nickname", "anchor_avatar_url", "douyin_id", "douyin_uid"):
        value = profile.get(field)
        if value and getattr(session, field) != value:
            setattr(session, field, str(value)[:500])
            changed = True
    return changed


def _needs_history_enrichment(session: LiveSession, has_related_assets: bool = False) -> bool:
    """判断历史场次是否还需要继续补齐详情。"""
    if session.detail_collection_status in (None, "", TaskStatus.PENDING, TaskStatus.RETRYABLE):
        return True
    if session.detail_collection_status != "complete":
        return False
    # 修复旧数据中的"假完整"：没有任何详情资产、核心指标或回放时应继续补齐。
    has_summary = any((
        session.total_viewers,
        session.viewed_count,
        session.peak_online_count,
        session.comments_count,
        session.interaction_count,
        session.private_message_count,
        session.new_followers,
    ))
    return not (has_related_assets or has_summary or session.stream_url)


def _repair_session_comment_integrity(db: Session) -> tuple[int, int]:
    """合并相同平台 roomId 的重复场次，并清理直播时间区间外的串场评论。"""
    duplicate_urls = [
        row[0]
        for row in (
            db.query(LiveSession.dashboard_url)
            .filter(LiveSession.dashboard_url.isnot(None))
            .group_by(LiveSession.dashboard_url)
            .having(func.count(LiveSession.id) > 1)
            .all()
        )
    ]
    merged_count = 0
    generic_child_tables = (
        "high_intent_users", "analysis_reports", "leads", "asr_tasks",
        "transcript_full_texts", "transcript_segments", "knowledge_base", "scraper_tasks",
    )

    for dashboard_url in duplicate_urls:
        sessions = db.query(LiveSession).filter(LiveSession.dashboard_url == dashboard_url).all()

        def score(item: LiveSession) -> tuple[int, int]:
            asset_count = sum((
                db.query(Comment).filter(Comment.session_id == item.id).count(),
                db.query(LiveMetric).filter(LiveMetric.session_id == item.id).count(),
                db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == item.id).count(),
                db.query(StreamSource).filter(StreamSource.session_id == item.id).count(),
            ))
            summary_count = sum(bool(getattr(item, field, None)) for field in (
                "total_viewers", "peak_online_count", "comments_count", "interaction_count", "stream_url",
            ))
            return asset_count + summary_count * 10, item.id

        canonical = max(sessions, key=score)
        duplicate_ids = [item.id for item in sessions if item.id != canonical.id]
        if not duplicate_ids:
            continue

        # 先迁移全部强外键子记录，再去重，最后才能安全删除父场次。
        for model in (Comment, LiveMetric, LiveAudienceProfile, StreamSource):
            db.query(model).filter(model.session_id.in_(duplicate_ids)).update(
                {model.session_id: canonical.id}, synchronize_session=False
            )
        for table_name in generic_child_tables:
            db.execute(
                text(f"UPDATE `{table_name}` SET session_id = :canonical WHERE session_id IN ({','.join(map(str, duplicate_ids))})"),
                {"canonical": canonical.id},
            )
        db.flush()

        seen_comments = set()
        for row in db.query(Comment).filter(Comment.session_id == canonical.id).order_by(Comment.id):
            identity = _comment_identity(row.user_nickname, row.comment_content or "", row.comment_time, row.user_sec_uid)
            if identity in seen_comments:
                db.delete(row)
            else:
                seen_comments.add(identity)
        for model, identity_getter in (
            (LiveMetric, lambda row: row.metric_time),
            (LiveAudienceProfile, lambda row: (row.dimension_type, row.dimension_name)),
        ):
            seen = set()
            for row in db.query(model).filter(model.session_id == canonical.id).order_by(model.id):
                identity = identity_getter(row)
                if identity in seen:
                    db.delete(row)
                else:
                    seen.add(identity)
        db.flush()
        db.query(LiveSession).filter(LiveSession.id.in_(duplicate_ids)).delete(synchronize_session=False)
        merged_count += len(duplicate_ids)
        db.flush()
        canonical.comments_count = db.query(Comment).filter(Comment.session_id == canonical.id).count()

    db.flush()
    invalid_comments = []
    for comment, session in db.query(Comment, LiveSession).join(LiveSession, LiveSession.id == Comment.session_id):
        if not _comment_belongs_to_session(comment.comment_time, session.live_start_time, session.live_end_time):
            invalid_comments.append(comment)
    for comment in invalid_comments:
        db.delete(comment)
    db.commit()
    return merged_count, len(invalid_comments)
