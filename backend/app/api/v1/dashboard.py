"""业务仪表盘汇总 API。"""

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.comments import Comment
from app.models.live_sessions import LiveSession
from app.models.review import ReviewActionItem
from app.schemas.dashboard import AnchorSummaryItem, AnchorSummaryResponse, DashboardSummaryResponse


router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


def _date_filter(query, model, start_date: date | None, end_date: date | None):
    """如果传了日期范围，对查询加 WHERE live_start_time BETWEEN 过滤。"""
    if start_date:
        query = query.filter(model.live_start_time >= start_date)
    if end_date:
        query = query.filter(model.live_start_time < end_date + timedelta(days=1))
    return query


def _serialize_summary(row, high_intent_comment_count: int = 0, open_review_action_count: int = 0) -> dict:
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
        "high_intent_comment_count": int(high_intent_comment_count or 0),
        "total_private_messages": int(row.total_private_messages or 0),
        "total_leads": total_leads,
        "total_ad_cost": round(total_ad_cost, 2),
        "average_lead_cost": round(total_ad_cost / total_leads, 2) if total_leads else 0,
        "open_review_action_count": int(open_review_action_count or 0),
    }


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    start_date: date | None = Query(default=None, description="开始日期（含），如 2026-07-20"),
    end_date: date | None = Query(default=None, description="结束日期（含），如 2026-07-20"),
    db: Session = Depends(get_db),
):
    """返回基于真实直播场次的核心经营数据，支持日期范围筛选。"""
    base_query = db.query(
        func.count(LiveSession.id).label("session_count"),
        func.count(distinct(case((LiveSession.douyin_id != "", LiveSession.douyin_id)))).label("anchor_count"),
        func.sum(case((LiveSession.live_status == "live", 1), else_=0)).label("live_session_count"),
        func.sum(case((LiveSession.detail_collection_status == "complete", 1), else_=0)).label("detail_complete_count"),
        func.coalesce(func.sum(LiveSession.total_viewers), 0).label("total_viewers"),
        func.coalesce(func.sum(LiveSession.comments_count), 0).label("total_comments"),
        func.coalesce(func.sum(LiveSession.private_message_count), 0).label("total_private_messages"),
        func.coalesce(func.sum(LiveSession.leads_count), 0).label("total_leads"),
        func.coalesce(func.sum(LiveSession.ad_cost), 0).label("total_ad_cost"),
    )
    base_query = _date_filter(base_query, LiveSession, start_date, end_date)
    row = base_query.one()

    # 高意向评论数：也按场次日期范围过滤
    comment_query = db.query(func.count(Comment.id)).filter(Comment.is_high_intent == 1)
    if start_date:
        comment_query = comment_query.filter(Comment.comment_time >= start_date)
    if end_date:
        comment_query = comment_query.filter(Comment.comment_time < end_date + timedelta(days=1))
    high_intent_comment_count = comment_query.scalar() or 0

    # 待办复盘：按 session 日期范围过滤
    action_query = db.query(func.count(ReviewActionItem.id)).filter(
        ReviewActionItem.status.in_(("pending", "in_progress"))
    )
    if start_date or end_date:
        action_query = action_query.join(LiveSession, ReviewActionItem.session_id == LiveSession.id)
        action_query = _date_filter(action_query, LiveSession, start_date, end_date)
    open_review_action_count = action_query.scalar() or 0

    return _serialize_summary(row, high_intent_comment_count, open_review_action_count)


@router.get("/summary/by-anchor", response_model=AnchorSummaryResponse)
def get_dashboard_summary_by_anchor(
    start_date: date | None = Query(default=None, description="开始日期（含）"),
    end_date: date | None = Query(default=None, description="结束日期（含）"),
    db: Session = Depends(get_db),
):
    """按主播（douyin_id）分组汇总经营指标，用于首页主播明细表。"""
    query = db.query(
        LiveSession.douyin_id,
        LiveSession.anchor_name,
        LiveSession.anchor_avatar_url,
        func.count(LiveSession.id).label("session_count"),
        func.coalesce(func.sum(LiveSession.total_viewers), 0).label("total_viewers"),
        func.coalesce(func.sum(LiveSession.comments_count), 0).label("total_comments"),
        func.coalesce(func.sum(LiveSession.private_message_count), 0).label("total_private_messages"),
        func.coalesce(func.sum(LiveSession.leads_count), 0).label("total_leads"),
        func.coalesce(func.sum(LiveSession.ad_cost), 0).label("total_ad_cost"),
        func.coalesce(func.sum(LiveSession.interaction_count), 0).label("total_interactions"),
        func.coalesce(func.sum(LiveSession.new_followers), 0).label("total_new_followers"),
    ).filter(LiveSession.douyin_id != "")
    query = _date_filter(query, LiveSession, start_date, end_date)
    query = query.group_by(LiveSession.douyin_id, LiveSession.anchor_name, LiveSession.anchor_avatar_url).order_by(
        func.count(LiveSession.id).desc()
    )

    rows = query.all()
    anchors: list[dict[str, Any]] = []
    for row in rows:
        anchors.append({
            "douyin_id": row.douyin_id or "",
            "anchor_name": row.anchor_name or "",
            "anchor_avatar_url": row.anchor_avatar_url or "",
            "session_count": int(row.session_count or 0),
            "total_viewers": int(row.total_viewers or 0),
            "total_comments": int(row.total_comments or 0),
            "total_private_messages": int(row.total_private_messages or 0),
            "total_leads": int(row.total_leads or 0),
            "total_ad_cost": round(float(row.total_ad_cost or 0), 2),
            "total_interactions": int(row.total_interactions or 0),
            "total_new_followers": int(row.total_new_followers or 0),
        })

    # 计算汇总行（前端可直接用 summary 接口，这里作为校验用）
    total = {
        "session_count": sum(a["session_count"] for a in anchors),
        "total_viewers": sum(a["total_viewers"] for a in anchors),
        "total_comments": sum(a["total_comments"] for a in anchors),
        "total_private_messages": sum(a["total_private_messages"] for a in anchors),
        "total_leads": sum(a["total_leads"] for a in anchors),
        "total_ad_cost": round(sum(a["total_ad_cost"] for a in anchors), 2),
        "total_interactions": sum(a["total_interactions"] for a in anchors),
        "total_new_followers": sum(a["total_new_followers"] for a in anchors),
    }
    return {"anchors": anchors, "total": total}
