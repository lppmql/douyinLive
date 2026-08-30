"""基于真实业务源表的原生经营仪表盘 API。"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.comments import Comment
from app.models.live_sessions import LiveSession
from app.models.review import ReviewActionItem
from app.schemas.dashboard import (
    AnchorSummaryResponse,
    DashboardOperationsResponse,
    DashboardSummaryResponse,
)
from app.services.live_session_selector import (
    build_session_anchor_key_expression,
    build_session_selector_condition,
)


router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


def _session_condition(
    start_date: date | None,
    end_date: date | None,
    anchor_key: str | None,
):
    """复用公共场次选择器口径，确保主播键和日期边界全项目一致。"""
    try:
        return build_session_selector_condition(
            anchor_key=anchor_key,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _serialize_summary(
    row,
    high_intent_comment_count: int = 0,
    open_review_action_count: int = 0,
) -> dict[str, Any]:
    session_count = int(row.session_count or 0)
    total_leads = int(row.total_leads or 0)
    total_ad_cost = float(row.total_ad_cost or 0)
    total_viewers = int(row.total_viewers or 0)
    total_private_messages = int(row.total_private_messages or 0)
    detail_complete_count = int(row.detail_complete_count or 0)
    return {
        "anchor_count": int(row.anchor_count or 0),
        "session_count": session_count,
        "live_session_count": int(row.live_session_count or 0),
        "detail_complete_count": detail_complete_count,
        "detail_completion_rate": round(detail_complete_count / session_count * 100, 1)
        if session_count
        else 0,
        "total_viewers": total_viewers,
        "total_comments": int(row.total_comments or 0),
        "high_intent_comment_count": int(high_intent_comment_count or 0),
        "total_private_messages": total_private_messages,
        "total_leads": total_leads,
        "total_ad_cost": round(total_ad_cost, 2),
        "average_lead_cost": round(total_ad_cost / total_leads, 2)
        if total_leads
        else 0,
        "private_message_rate": round(total_private_messages / total_viewers * 100, 2)
        if total_viewers
        else 0,
        "lead_conversion_rate": round(total_leads / total_viewers * 100, 2)
        if total_viewers
        else 0,
        "total_exposure_users": int(getattr(row, "total_exposure_users", 0) or 0),
        "total_enter_users": int(getattr(row, "total_enter_users", 0) or 0),
        "total_card_click_users": int(getattr(row, "total_card_click_users", 0) or 0),
        "open_review_action_count": int(open_review_action_count or 0),
    }


def _build_summary(
    db: Session,
    start_date: date | None,
    end_date: date | None,
    anchor_key: str | None,
) -> dict[str, Any]:
    condition = _session_condition(start_date, end_date, anchor_key)
    row = (
        db.query(
            func.count(LiveSession.id).label("session_count"),
            func.count(distinct(build_session_anchor_key_expression())).label(
                "anchor_count"
            ),
            func.sum(case((LiveSession.live_status == "live", 1), else_=0)).label(
                "live_session_count"
            ),
            func.sum(
                case((LiveSession.detail_collection_status == "complete", 1), else_=0)
            ).label("detail_complete_count"),
            func.coalesce(func.sum(LiveSession.total_viewers), 0).label("total_viewers"),
            func.coalesce(func.sum(LiveSession.comments_count), 0).label("total_comments"),
            func.coalesce(func.sum(LiveSession.private_message_count), 0).label(
                "total_private_messages"
            ),
            func.coalesce(func.sum(LiveSession.leads_count), 0).label("total_leads"),
            func.coalesce(func.sum(LiveSession.ad_cost), 0).label("total_ad_cost"),
            func.coalesce(func.sum(LiveSession.live_exposure_users), 0).label(
                "total_exposure_users"
            ),
            func.coalesce(func.sum(LiveSession.live_enter_users), 0).label(
                "total_enter_users"
            ),
            func.coalesce(func.sum(LiveSession.card_click_users), 0).label(
                "total_card_click_users"
            ),
        )
        .filter(condition)
        .one()
    )

    high_intent_comment_count = (
        db.query(func.count(Comment.id))
        .join(LiveSession, Comment.session_id == LiveSession.id)
        .filter(Comment.is_high_intent == 1, condition)
        .scalar()
        or 0
    )
    open_review_action_count = (
        db.query(func.count(ReviewActionItem.id))
        .join(LiveSession, ReviewActionItem.session_id == LiveSession.id)
        .filter(
            ReviewActionItem.status.in_(("pending", "in_progress")),
            condition,
        )
        .scalar()
        or 0
    )
    return _serialize_summary(
        row,
        high_intent_comment_count=high_intent_comment_count,
        open_review_action_count=open_review_action_count,
    )


def _build_anchor_summary(
    db: Session,
    start_date: date | None,
    end_date: date | None,
    anchor_key: str | None,
) -> dict[str, Any]:
    condition = _session_condition(start_date, end_date, anchor_key)
    stable_anchor_key = build_session_anchor_key_expression()
    agg_sub = (
        db.query(
            stable_anchor_key.label("anchor_key"),
            func.count(LiveSession.id).label("session_count"),
            func.coalesce(func.sum(LiveSession.total_viewers), 0).label("total_viewers"),
            func.coalesce(func.sum(LiveSession.comments_count), 0).label("total_comments"),
            func.coalesce(func.sum(LiveSession.private_message_count), 0).label(
                "total_private_messages"
            ),
            func.coalesce(func.sum(LiveSession.leads_count), 0).label("total_leads"),
            func.coalesce(func.sum(LiveSession.ad_cost), 0).label("total_ad_cost"),
            func.coalesce(func.sum(LiveSession.interaction_count), 0).label(
                "total_interactions"
            ),
            func.coalesce(func.sum(LiveSession.new_followers), 0).label(
                "total_new_followers"
            ),
        )
        .filter(condition)
        .group_by(stable_anchor_key)
        .subquery()
    )
    # 历史补采会产生更高的自增 ID，但它不一定是主播最新开播场次；这里和公共
    # 主播选择接口统一按“开播时间倒序、ID 倒序”选择身份与头像快照。
    ranked_snapshots = (
        db.query(
            LiveSession.id.label("session_id"),
            stable_anchor_key.label("anchor_key"),
            func.row_number().over(
                partition_by=stable_anchor_key,
                order_by=(LiveSession.live_start_time.desc(), LiveSession.id.desc()),
            ).label("snapshot_rank"),
        )
        .filter(condition)
        .subquery()
    )
    rows = (
        db.query(
            agg_sub.c.anchor_key,
            LiveSession.douyin_id,
            LiveSession.anchor_name,
            LiveSession.anchor_nickname,
            LiveSession.anchor_avatar_url,
            LiveSession.id.label("anchor_avatar_session_id"),
            agg_sub.c.session_count,
            agg_sub.c.total_viewers,
            agg_sub.c.total_comments,
            agg_sub.c.total_private_messages,
            agg_sub.c.total_leads,
            agg_sub.c.total_ad_cost,
            agg_sub.c.total_interactions,
            agg_sub.c.total_new_followers,
        )
        .join(
            ranked_snapshots,
            (ranked_snapshots.c.anchor_key == agg_sub.c.anchor_key)
            & (ranked_snapshots.c.snapshot_rank == 1),
        )
        .join(LiveSession, LiveSession.id == ranked_snapshots.c.session_id)
        .order_by(agg_sub.c.total_leads.desc(), agg_sub.c.session_count.desc())
        .all()
    )
    anchors = [
        {
            "anchor_key": row.anchor_key or "",
            "douyin_id": row.douyin_id or "",
            "anchor_name": row.anchor_name or row.anchor_nickname or "未知主播",
            "anchor_avatar_url": row.anchor_avatar_url or "",
            "anchor_avatar_session_id": row.anchor_avatar_session_id,
            "session_count": int(row.session_count or 0),
            "total_viewers": int(row.total_viewers or 0),
            "total_comments": int(row.total_comments or 0),
            "total_private_messages": int(row.total_private_messages or 0),
            "total_leads": int(row.total_leads or 0),
            "total_ad_cost": round(float(row.total_ad_cost or 0), 2),
            "total_interactions": int(row.total_interactions or 0),
            "total_new_followers": int(row.total_new_followers or 0),
        }
        for row in rows
    ]
    total_keys = (
        "session_count",
        "total_viewers",
        "total_comments",
        "total_private_messages",
        "total_leads",
        "total_ad_cost",
        "total_interactions",
        "total_new_followers",
    )
    return {
        "anchors": anchors,
        "total": {
            key: round(sum(float(item[key]) for item in anchors), 2)
            if key == "total_ad_cost"
            else int(sum(int(item[key]) for item in anchors))
            for key in total_keys
        },
    }


def _build_trend(
    db: Session,
    start_date: date | None,
    end_date: date | None,
    anchor_key: str | None,
) -> list[dict[str, Any]]:
    date_key = func.date(LiveSession.live_start_time)
    rows = (
        db.query(
            date_key.label("date_key"),
            func.count(LiveSession.id).label("session_count"),
            func.coalesce(func.sum(LiveSession.total_viewers), 0).label("total_viewers"),
            func.coalesce(func.sum(LiveSession.comments_count), 0).label("total_comments"),
            func.coalesce(func.sum(LiveSession.private_message_count), 0).label(
                "total_private_messages"
            ),
            func.coalesce(func.sum(LiveSession.leads_count), 0).label("total_leads"),
            func.coalesce(func.sum(LiveSession.ad_cost), 0).label("total_ad_cost"),
        )
        .filter(
            LiveSession.live_start_time.isnot(None),
            _session_condition(start_date, end_date, anchor_key),
        )
        .group_by(date_key)
        .order_by(date_key.asc())
        .all()
    )
    return [
        {
            "date_key": str(row.date_key),
            "session_count": int(row.session_count or 0),
            "total_viewers": int(row.total_viewers or 0),
            "total_comments": int(row.total_comments or 0),
            "total_private_messages": int(row.total_private_messages or 0),
            "total_leads": int(row.total_leads or 0),
            "total_ad_cost": round(float(row.total_ad_cost or 0), 2),
        }
        for row in rows
    ]


def _build_recent_sessions(
    db: Session,
    start_date: date | None,
    end_date: date | None,
    anchor_key: str | None,
) -> list[dict[str, Any]]:
    rows = (
        db.query(LiveSession)
        .filter(_session_condition(start_date, end_date, anchor_key))
        .order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
        .limit(30)
        .all()
    )
    result = []
    for row in rows:
        leads = int(row.leads_count or 0)
        ad_cost = float(row.ad_cost or 0)
        result.append(
            {
                "id": row.id,
                "anchor_name": row.anchor_name or row.anchor_nickname or "未知主播",
                "anchor_avatar_url": row.anchor_avatar_url or "",
                "douyin_id": row.douyin_id or "",
                "session_title": row.session_title or f"直播场次 #{row.id}",
                "live_start_time": row.live_start_time,
                "live_duration_seconds": int(row.live_duration_seconds or 0),
                "total_viewers": int(row.total_viewers or 0),
                "total_comments": int(row.comments_count or 0),
                "total_private_messages": int(row.private_message_count or 0),
                "total_leads": leads,
                "total_ad_cost": round(ad_cost, 2),
                "lead_cost": round(ad_cost / leads, 2) if leads else 0,
            }
        )
    return result


def _build_funnel(summary: dict[str, Any]) -> list[dict[str, Any]]:
    stages = (
        ("曝光", int(summary["total_exposure_users"])),
        ("进入直播间", int(summary["total_enter_users"])),
        ("卡片点击", int(summary["total_card_click_users"])),
        ("站内私信", int(summary["total_private_messages"])),
        ("确认留资", int(summary["total_leads"])),
    )
    result = []
    previous = 0
    for index, (label, value) in enumerate(stages):
        result.append(
            {
                "label": label,
                "value": value,
                "step_rate": 100.0
                if index == 0 and value
                else round(value / previous * 100, 2)
                if previous
                else 0,
            }
        )
        previous = value
    return result


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    start_date: date | None = Query(default=None, description="开始日期（含）"),
    end_date: date | None = Query(default=None, description="结束日期（含）"),
    anchor_key: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db),
):
    """返回真实直播场次核心经营数据，支持日期和主播筛选。"""
    return _build_summary(db, start_date, end_date, anchor_key)


@router.get("/summary/by-anchor", response_model=AnchorSummaryResponse)
def get_dashboard_summary_by_anchor(
    start_date: date | None = Query(default=None, description="开始日期（含）"),
    end_date: date | None = Query(default=None, description="结束日期（含）"),
    anchor_key: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db),
):
    """按稳定主播键分组汇总经营指标。"""
    return _build_anchor_summary(db, start_date, end_date, anchor_key)


@router.get("/operations", response_model=DashboardOperationsResponse)
def get_dashboard_operations(
    start_date: date | None = Query(default=None, description="开始日期（含）"),
    end_date: date | None = Query(default=None, description="结束日期（含）"),
    anchor_key: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db),
):
    """一次返回原生大屏所需数据，减少前端重复请求和口径漂移。"""
    summary = _build_summary(db, start_date, end_date, anchor_key)
    anchor_summary = _build_anchor_summary(db, start_date, end_date, anchor_key)
    return {
        "summary": summary,
        "anchors": anchor_summary["anchors"],
        "trend": _build_trend(db, start_date, end_date, anchor_key),
        "funnel": _build_funnel(summary),
        "recent_sessions": _build_recent_sessions(
            db, start_date, end_date, anchor_key
        ),
    }
