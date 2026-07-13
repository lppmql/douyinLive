"""评论汇总同步 — comments → de_anchor_comment_summary"""
from sqlalchemy import func
from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.comments import Comment
from app.models.de_tables import DeAnchorCommentSummary


def sync_comment_summary(db, session_id: int):
    """同步评论汇总数据"""
    # 先删除旧数据
    db.query(DeAnchorCommentSummary).filter(
        DeAnchorCommentSummary.session_id == session_id
    ).delete()

    session = db.query(LiveSession).get(session_id)
    if not session:
        return

    room = db.query(LiveRoom).get(session.room_id) if session.room_id else None

    total = db.query(func.count(Comment.id)).filter(
        Comment.session_id == session_id
    ).scalar() or 0

    high_intent = db.query(func.count(Comment.id)).filter(
        Comment.session_id == session_id,
        Comment.is_high_intent == 1,
    ).scalar() or 0

    positive = db.query(func.count(Comment.id)).filter(
        Comment.session_id == session_id,
        Comment.sentiment == "positive",
    ).scalar() or 0

    neutral = db.query(func.count(Comment.id)).filter(
        Comment.session_id == session_id,
        Comment.sentiment == "neutral",
    ).scalar() or 0

    negative = db.query(func.count(Comment.id)).filter(
        Comment.session_id == session_id,
        Comment.sentiment == "negative",
    ).scalar() or 0

    summary = DeAnchorCommentSummary(
        session_id=session_id,
        anchor_name=session.anchor_name or (room.anchor_name if room else None),
        session_title=session.session_title,
        stat_date=session.live_start_time.date() if session.live_start_time else None,
        total_comments=total,
        high_intent_count=high_intent,
        positive_count=positive,
        neutral_count=neutral,
        negative_count=negative,
    )
    db.add(summary)
    logger.info(f"  comment_summary: {total} 条评论")
