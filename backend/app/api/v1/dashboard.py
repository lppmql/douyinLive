"""业务仪表盘汇总 API。"""

from fastapi import APIRouter, Depends
from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_sessions import LiveSession


router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


def _serialize_summary(row) -> dict:
    session_count = int(row.session_count or 0)
    total_leads = int(row.total_leads or 0)
    total_ad_cost = float(row.total_ad_cost or 0)
    detail_complete_count = int(row.detail_complete_count or 0)
    return {
        "anchor_count": int(row.anchor_count or 0),
        "session_count": session_count,
        "live_session_count": int(row.live_session_count or 0),
        "detail_complete_count": detail_complete_count,
        "detail_completion_rate": round(detail_complete_count / session_count * 100, 1) if session_count else 0,
        "total_viewers": int(row.total_viewers or 0),
        "total_comments": int(row.total_comments or 0),
        "total_leads": total_leads,
        "total_ad_cost": round(total_ad_cost, 2),
        "average_lead_cost": round(total_ad_cost / total_leads, 2) if total_leads else 0,
    }


@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """返回基于真实直播场次的核心经营数据。"""
    row = db.query(
        func.count(LiveSession.id).label("session_count"),
        # 昵称会变更，同一主播可能出现多个历史昵称；抖音号才是稳定的去重口径。
        func.count(distinct(case((LiveSession.douyin_id != "", LiveSession.douyin_id)))).label("anchor_count"),
        func.sum(case((LiveSession.live_status == "live", 1), else_=0)).label("live_session_count"),
        func.sum(case((LiveSession.detail_collection_status == "complete", 1), else_=0)).label("detail_complete_count"),
        func.coalesce(func.sum(LiveSession.total_viewers), 0).label("total_viewers"),
        func.coalesce(func.sum(LiveSession.comments_count), 0).label("total_comments"),
        func.coalesce(func.sum(LiveSession.leads_count), 0).label("total_leads"),
        func.coalesce(func.sum(LiveSession.ad_cost), 0).label("total_ad_cost"),
    ).one()

    return _serialize_summary(row)
