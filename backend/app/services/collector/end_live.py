"""下播处理 — 汇总数据、更新场次记录、触发 DataEase 同步"""
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.leads import Lead
from app.models.stream_sources import StreamSource
from app.models.scraper_logs import ScraperLog
from app.services.sync import sync_session


async def process_live_end(db: Session, session_id: int):
    """
    下播处理：
    1. 聚合 live_metrics 统计
    2. 更新 live_sessions 最终数据
    3. 标记 stream_sources 为过期
    4. 同步 de_ 大屏表数据
    """
    try:
        session = db.query(LiveSession).get(session_id)
        if not session:
            logger.warning(f"session {session_id} 不存在")
            return

        # 聚合指标
        metrics_stats = db.query(
            func.max(LiveMetric.online_count).label("peak_online"),
            func.count(LiveMetric.id).label("metric_count"),
        ).filter(LiveMetric.session_id == session_id).first()

        comment_count = db.query(func.count(Comment.id)).filter(
            Comment.session_id == session_id
        ).scalar() or 0

        lead_count = db.query(func.count(Lead.id)).filter(
            Lead.session_id == session_id
        ).scalar() or 0

        # 更新场次
        now = datetime.utcnow()
        session.live_end_time = now
        session.live_status = "ended"
        if session.live_start_time:
            session.live_duration_seconds = int((now - session.live_start_time).total_seconds())
        if metrics_stats and metrics_stats.peak_online:
            session.peak_online_count = metrics_stats.peak_online
        session.comments_count = comment_count
        session.leads_count = lead_count

        # 标记流源为过期
        db.query(StreamSource).filter(
            StreamSource.session_id == session_id,
            StreamSource.status == "active",
        ).update({"status": "expired", "expires_at": now})

        # 记录日志
        log = ScraperLog(
            level="info",
            message=f"直播场次 {session_id} 已结束, 时长 {session.live_duration_seconds}s, "
                    f"评论 {comment_count}, 留资 {lead_count}",
        )
        db.add(log)
        db.commit()

        # 同步 de_ 大屏表
        try:
            sync_session(db, session_id)
        except Exception as sync_err:
            logger.error(f"DataEase 同步失败 session={session_id}: {sync_err}")

        logger.info(f"下播处理完成: session={session_id}")

    except Exception as e:
        logger.error(f"下播处理失败 session={session_id}: {e}")
        raise
