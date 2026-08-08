"""AI 剪辑候选的真实多信号特征。

只使用数据库已有的评论、互动指标、钩子和确认客资。分数用于候选排序，
不会把“时间上接近”写成确定因果；证据会随成片保存，供运营复查。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.comments import Comment
from app.models.lead_conversion_pairs import LeadConversionPair
from app.models.live_metrics import LiveMetric
from app.models.live_sessions import LiveSession
from app.services.analysis.session_conversion import build_session_conversion_analysis


def _relative_seconds(session: LiveSession, value) -> float | None:
    if not session.live_start_time or not value:
        return None
    return max(0.0, (value - session.live_start_time).total_seconds())


def _metric_delta(
    metrics: list[tuple[float, LiveMetric]],
    start: float,
    end: float,
) -> dict[str, int]:
    """计算窗口前后累计指标差；平台计数回退时按 0 处理，禁止产生负互动。"""
    before = next(
        (metric for seconds, metric in reversed(metrics) if seconds <= start), None
    )
    after = next(
        (metric for seconds, metric in reversed(metrics) if seconds <= end), None
    )
    if before is None or after is None:
        return {}
    fields = (
        "like_count",
        "comment_count",
        "follow_count",
        "enter_count",
        "clue_count",
        "windmill_click_count",
        "card_click_count",
    )
    return {
        field: max(
            0, int(getattr(after, field, 0) or 0) - int(getattr(before, field, 0) or 0)
        )
        for field in fields
    }


def build_multisignal_map(
    db: Session,
    session_id: int,
    units: list[Any],
) -> dict[int, dict[str, Any]]:
    """按 transcript_segment_id 返回候选信号与可解释分数。"""
    session = db.get(LiveSession, session_id)
    if not session or not units:
        return {}

    comments = (
        db.query(Comment)
        .filter(Comment.session_id == session_id)
        .order_by(Comment.comment_time.asc(), Comment.id.asc())
        .all()
    )
    comment_points = [
        (seconds, comment)
        for comment in comments
        if (seconds := _relative_seconds(session, comment.comment_time)) is not None
    ]
    metric_rows = (
        db.query(LiveMetric)
        .filter(LiveMetric.session_id == session_id)
        .order_by(LiveMetric.metric_time.asc(), LiveMetric.id.asc())
        .all()
    )
    metric_points = [
        (seconds, metric)
        for metric in metric_rows
        if (seconds := _relative_seconds(session, metric.metric_time)) is not None
    ]
    conversion = build_session_conversion_analysis(db, session, comments, len(comments))
    hook_events = [
        item for item in conversion.get("hook_events", []) if item.get("is_formal_hook")
    ]
    lead_rows = (
        db.query(LeadConversionPair)
        .filter(
            LeadConversionPair.session_id == session_id,
            LeadConversionPair.attribution_status == "attributed",
        )
        .all()
    )
    lead_seconds = [
        seconds
        for lead in lead_rows
        if (seconds := _relative_seconds(session, lead.converted_at)) is not None
    ]

    result: dict[int, dict[str, Any]] = {}
    for unit in units:
        if not unit.segment_id:
            continue
        start = float(unit.start)
        end = float(unit.end)
        # 评论允许延后 30 秒，覆盖主播一句话说完后观众才打字发出的正常延迟。
        nearby_comments = [
            comment
            for seconds, comment in comment_points
            if start <= seconds <= end + 30
        ]
        comment_count = len(nearby_comments)
        high_intent_count = sum(
            int(comment.is_high_intent or 0) == 1 for comment in nearby_comments
        )
        metric_deltas = _metric_delta(metric_points, max(0.0, start - 30), end + 30)
        overlapping_hooks = [
            hook
            for hook in hook_events
            if float(hook.get("end_seconds") or 0) >= start - 5
            and float(hook.get("start_seconds") or 0) <= end + 30
        ]
        related_leads = sum(
            int(hook.get("related_lead_count") or 0) for hook in overlapping_hooks
        )
        leads_after_5m = sum(
            1 for seconds in lead_seconds if end <= seconds <= end + 300
        )

        hook_score = 0
        if overlapping_hooks:
            strongest = max(
                (str(hook.get("strength") or "weak") for hook in overlapping_hooks),
                key={"weak": 1, "medium": 2, "strong": 3}.get,
            )
            hook_score = {"weak": 6, "medium": 12, "strong": 20}.get(strongest, 6)
        else:
            strongest = None
        interaction_score = min(20, comment_count * 2 + high_intent_count * 3)
        metric_score = min(
            20,
            int(metric_deltas.get("comment_count", 0)) * 2
            + int(metric_deltas.get("follow_count", 0)) * 3
            + min(8, int(metric_deltas.get("like_count", 0)) // 10)
            + min(5, int(metric_deltas.get("enter_count", 0)) // 5),
        )
        # 片段后 5 分钟客资只是时间邻近事实；只有片段同时覆盖正式钩子时才作为
        # 弱排序信号，避免普通话术因碰巧靠近客资时间而被误判成转化因果。
        lead_score = min(
            25,
            related_leads * 12 + (leads_after_5m * 5 if overlapping_hooks else 0),
        )
        transcript_score = min(20, round(float(unit.ai_score or 0) * 2))
        if unit.high_value:
            transcript_score = max(transcript_score, 15)
        total_score = (
            interaction_score
            + metric_score
            + hook_score
            + lead_score
            + transcript_score
        )

        result[int(unit.segment_id)] = {
            "signal_score": total_score,
            "comment_count": comment_count,
            "high_intent_comment_count": high_intent_count,
            "metric_deltas": metric_deltas,
            "hook_count": len(overlapping_hooks),
            "hook_strength": strongest,
            "hook_types": list(
                dict.fromkeys(
                    hook_type
                    for hook in overlapping_hooks
                    for hook_type in hook.get("hook_types", [])
                )
            ),
            "related_lead_count": related_leads,
            "lead_after_5m_count": leads_after_5m,
            "attribution_label": "客资与钩子/片段仅为时间窗关联，不代表确定因果",
        }
    return result
