"""DataEase 宽表状态与增量同步 API。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.de_tables import (
    DeAnchorAiAnalysisSummary,
    DeAnchorAudienceProfile,
    DeAnchorCommentSummary,
    DeAnchorRealtimeMetrics,
    DeAnchorTranscriptSummary,
    DeLiveSessionAnchorSummary,
)
from app.models.live_sessions import LiveSession
from app.services.sync import sync_pending_complete_sessions
from app.services.sync.de_sync import source_data_outdated_condition

router = APIRouter(prefix="/dataease", tags=["DataEase"])


def _coverage(source_count: int, synced_count: int, outdated_count: int) -> tuple[int, int, float]:
    pending_count = max(0, source_count - synced_count + outdated_count)
    fresh_count = max(0, source_count - pending_count)
    rate = round(fresh_count / source_count * 100, 1) if source_count else 100.0
    return fresh_count, pending_count, rate


def _status(db: Session) -> dict:
    complete_filter = LiveSession.detail_collection_status == "complete"
    source_count = db.query(func.count(LiveSession.id)).filter(complete_filter).scalar() or 0
    synced_count = db.query(func.count(LiveSession.id)).join(
        DeLiveSessionAnchorSummary,
        DeLiveSessionAnchorSummary.session_id == LiveSession.id,
    ).filter(complete_filter).scalar() or 0
    outdated_count = db.query(func.count(LiveSession.id)).join(
        DeLiveSessionAnchorSummary,
        DeLiveSessionAnchorSummary.session_id == LiveSession.id,
    ).filter(
        complete_filter,
        source_data_outdated_condition(),
    ).scalar() or 0
    fresh_count, pending_count, coverage_rate = _coverage(source_count, synced_count, outdated_count)
    last_synced_at: datetime | None = db.query(func.max(DeLiveSessionAnchorSummary.updated_at)).scalar()
    return {
        "source_session_count": source_count,
        "synced_session_count": fresh_count,
        "pending_session_count": pending_count,
        "outdated_session_count": outdated_count,
        "coverage_rate": coverage_rate,
        "metric_row_count": db.query(func.count(DeAnchorRealtimeMetrics.id)).scalar() or 0,
        "profile_row_count": db.query(func.count(DeAnchorAudienceProfile.id)).scalar() or 0,
        "comment_summary_count": db.query(func.count(DeAnchorCommentSummary.id)).scalar() or 0,
        "transcript_summary_count": db.query(func.count(DeAnchorTranscriptSummary.id)).scalar() or 0,
        "ai_summary_count": db.query(func.count(DeAnchorAiAnalysisSummary.id)).scalar() or 0,
        "last_synced_at": last_synced_at,
    }


@router.get("/status")
def get_dataease_status(db: Session = Depends(get_db)):
    """返回业务完整场次到 DataEase 宽表的真实覆盖情况。"""
    return _status(db)


@router.post("/sync")
def sync_dataease(
    limit: int = Query(100, ge=1, le=500),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    """增量同步缺失/过期场次；force=true 时强制重建最近完整场次。"""
    result = sync_pending_complete_sessions(db, limit=limit, force=force)
    return {"status": "ok" if not result["failed_count"] else "partial", **result, "dataease": _status(db)}
