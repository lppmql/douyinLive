"""
DataEase 同步主入口

用法:
    from app.services.sync import sync_all, sync_session

    sync_all(db)          # 全量同步
    sync_session(db, 1)   # 单场同步（下播时触发）
"""
from app.core.logger import logger
from sqlalchemy import exists, or_, select

from app.models.analysis_reports import AnalysisReport
from app.models.comments import Comment
from app.models.de_tables import (
    DeAnchorAiAnalysisSummary,
    DeAnchorAudienceProfile,
    DeAnchorCommentSummary,
    DeAnchorConversionFunnel,
    DeAnchorRealtimeMetrics,
    DeAnchorTranscriptSummary,
    DeLiveSessionAnchorSummary,
)
from app.models.live_sessions import LiveSession
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.transcript_segments import TranscriptSegment
from app.services.sync.analysis_sync import sync_ai_analysis_summary
from app.services.sync.session_sync import sync_session_summary, sync_realtime_metrics, sync_conversion_funnel
from app.services.sync.profile_sync import sync_audience_profiles
from app.services.sync.comment_sync import sync_comment_summary
from app.services.sync.transcript_sync import sync_transcript_summary


def sync_session(db, session_id: int):
    """同步单场直播的所有 de_ 数据（下播时调用）"""
    logger.info(f"开始同步 session {session_id} 到 de_ 表")
    sync_session_summary(db, session_id)
    sync_realtime_metrics(db, session_id)
    sync_conversion_funnel(db, session_id)
    sync_audience_profiles(db, session_id)
    sync_comment_summary(db, session_id)
    sync_transcript_summary(db, session_id)
    sync_ai_analysis_summary(db, session_id)
    db.commit()
    logger.info(f"session {session_id} 同步完成")


def sync_sessions(db, session_ids: list[int]) -> dict:
    """逐场提交，单场失败不会回滚其他已成功的 DataEase 数据。"""
    result = {"selected_count": len(session_ids), "synced_count": 0, "failed_count": 0, "errors": []}
    for session_id in session_ids:
        try:
            sync_session(db, session_id)
            result["synced_count"] += 1
        except Exception as exc:
            logger.exception("DataEase 同步失败 session=%s: %s", session_id, exc)
            db.rollback()
            result["failed_count"] += 1
            if len(result["errors"]) < 10:
                result["errors"].append({"session_id": session_id, "message": str(exc)[:300]})
    return result


def source_data_outdated_condition():
    """任一业务源表比场次汇总宽表新时，该场次需要重新同步。"""
    return or_(
        LiveSession.updated_at > DeLiveSessionAnchorSummary.updated_at,
        exists().where(
            LiveMetric.session_id == LiveSession.id,
            LiveMetric.updated_at > DeLiveSessionAnchorSummary.updated_at,
        ),
        exists().where(
            Comment.session_id == LiveSession.id,
            Comment.updated_at > DeLiveSessionAnchorSummary.updated_at,
        ),
        exists().where(
            LiveAudienceProfile.session_id == LiveSession.id,
            LiveAudienceProfile.updated_at > DeLiveSessionAnchorSummary.updated_at,
        ),
        exists().where(
            TranscriptSegment.session_id == LiveSession.id,
            TranscriptSegment.updated_at > DeLiveSessionAnchorSummary.updated_at,
        ),
        exists().where(
            AnalysisReport.session_id == LiveSession.id,
            AnalysisReport.updated_at > DeLiveSessionAnchorSummary.updated_at,
        ),
    )


def pending_complete_session_ids(db, limit: int | None = 100, force: bool = False) -> list[int]:
    """选择已完整但尚未同步或业务数据比宽表更新的场次。"""
    query = db.query(LiveSession.id).outerjoin(
        DeLiveSessionAnchorSummary,
        DeLiveSessionAnchorSummary.session_id == LiveSession.id,
    ).filter(LiveSession.detail_collection_status == "complete")
    if not force:
        query = query.filter(or_(
            DeLiveSessionAnchorSummary.id.is_(None),
            source_data_outdated_condition(),
        ))
    query = query.order_by(LiveSession.updated_at.desc(), LiveSession.id.desc())
    if limit is not None:
        query = query.limit(limit)
    return [row[0] for row in query.all()]


def cleanup_stale_dataease_rows(db) -> int:
    """删除不再属于完整场次的宽表行，避免 DataEase 继续统计历史脏数据。"""
    valid_ids = select(LiveSession.id).where(LiveSession.detail_collection_status == "complete")
    removed = 0
    for model in (
        DeAnchorAiAnalysisSummary,
        DeAnchorAudienceProfile,
        DeAnchorCommentSummary,
        DeAnchorConversionFunnel,
        DeAnchorRealtimeMetrics,
        DeAnchorTranscriptSummary,
        DeLiveSessionAnchorSummary,
    ):
        removed += db.query(model).filter(~model.session_id.in_(valid_ids)).delete(synchronize_session=False)
    db.commit()
    return removed


def sync_pending_complete_sessions(db, limit: int | None = 100, force: bool = False) -> dict:
    """增量同步 DataEase 所需的完整场次。"""
    removed = cleanup_stale_dataease_rows(db)
    result = sync_sessions(db, pending_complete_session_ids(db, limit=limit, force=force))
    result["removed_stale_row_count"] = removed
    return result


def sync_all(db):
    """维护脚本全量重建所有完整场次，并清除不完整场次的历史宽表。"""
    removed = cleanup_stale_dataease_rows(db)
    session_ids = [
        row[0]
        for row in db.query(LiveSession.id)
        .filter(LiveSession.detail_collection_status == "complete")
        .order_by(LiveSession.id)
        .all()
    ]
    logger.info("开始全量同步，共 %s 个场次", len(session_ids))
    result = sync_sessions(db, session_ids)
    result["removed_stale_row_count"] = removed
    logger.info("全量同步完成: 成功=%s 失败=%s", result["synced_count"], result["failed_count"])
    return result
