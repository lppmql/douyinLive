"""话术汇总同步 — transcript_segments → de_anchor_transcript_summary"""
from sqlalchemy import func
from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.transcript_segments import TranscriptSegment
from app.models.transcript_full_texts import TranscriptFullText
from app.models.de_tables import DeAnchorTranscriptSummary


def sync_transcript_summary(db, session_id: int):
    """同步话术汇总数据"""
    # 先删除旧数据
    db.query(DeAnchorTranscriptSummary).filter(
        DeAnchorTranscriptSummary.session_id == session_id
    ).delete()

    session = db.query(LiveSession).get(session_id)
    if not session:
        return

    room = db.query(LiveRoom).get(session.room_id) if session.room_id else None

    total_segments = db.query(func.count(TranscriptSegment.id)).filter(
        TranscriptSegment.session_id == session_id
    ).scalar() or 0

    # 完整文本长度
    full_text = db.query(TranscriptFullText).filter(
        TranscriptFullText.session_id == session_id
    ).first()
    total_text_length = len(full_text.full_text) if full_text and full_text.full_text else 0

    # 平均 AI 评分
    avg_score = db.query(func.avg(TranscriptSegment.ai_score)).filter(
        TranscriptSegment.session_id == session_id,
        TranscriptSegment.ai_score.isnot(None),
    ).scalar()
    avg_ai_score = float(avg_score) if avg_score else None

    # ASR 状态（取最新 segment 的状态）
    latest_seg = db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id == session_id
    ).order_by(TranscriptSegment.id.desc()).first()
    asr_status = latest_seg.asr_status if latest_seg else "pending"

    summary = DeAnchorTranscriptSummary(
        session_id=session_id,
        anchor_name=session.anchor_name or (room.anchor_name if room else None),
        session_title=session.session_title,
        total_segments=total_segments,
        total_text_length=total_text_length,
        avg_ai_score=avg_ai_score,
        asr_status=asr_status,
    )
    db.add(summary)
    logger.info(f"  transcript_summary: {total_segments} 个分段")
