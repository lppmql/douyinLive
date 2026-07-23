"""下播处理：只完成场次收口，后续模块由各自开关独立控制。"""
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.leads import Lead
from app.models.stream_sources import StreamSource
from app.services.asr.control import get_asr_runtime_status
from app.services.asr.queue import queue_auto_transcriptions
from app.services.collector.log_service import add_collector_log


async def process_live_end(db: Session, session_id: int):
    """
    下播处理：
    1. 聚合 live_metrics 统计
    2. 更新 live_sessions 最终数据
    3. 标记 stream_sources 为过期
    4. ASR 开关开启时，把该场话术转写加入独立队列
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
        # 企业后台的场次时间按服务器本地时区保存为无时区 datetime，结束时间需保持一致。
        now = datetime.now()
        session.live_end_time = now
        session.live_status = "ended"
        if session.live_start_time:
            session.live_duration_seconds = max(0, int((now - session.live_start_time).total_seconds()))
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
        add_collector_log(
            db,
            session=session,
            level="info",
            stage="live_end",
            event_type="session_ended",
            message=(
                f"主播 {session.anchor_name or session.anchor_nickname or '未知主播'}，"
                f"场次 #{session_id} 已结束，时长 {session.live_duration_seconds} 秒，"
                f"评论 {comment_count} 条，留资 {lead_count} 条"
            ),
            details={
                "duration_seconds": session.live_duration_seconds,
                "comment_count": comment_count,
                "lead_count": lead_count,
                "dataease_status": "等待独立同步",
            },
        )
        db.commit()

        if getattr(session, "detail_collection_status", None) == "complete":
            runtime = get_asr_runtime_status()
            if runtime["enabled"]:
                queued = queue_auto_transcriptions(db, limit=1, session_ids=[session_id])
                logger.info("下播话术自动排队: session=%s created=%s", session_id, queued["created_count"])

        logger.info(f"下播处理完成: session={session_id}")

    except Exception as e:
        logger.error(f"下播处理失败 session={session_id}: {e}")
        raise
