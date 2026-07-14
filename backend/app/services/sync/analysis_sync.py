"""AI 分析汇总同步 — analysis_reports → de_anchor_ai_analysis_summary。"""
from sqlalchemy import func

from app.models.analysis_reports import AnalysisReport
from app.models.de_tables import DeAnchorAiAnalysisSummary
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession


def _score_value(content: dict | None, key: str) -> float | None:
    value = (content or {}).get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def sync_ai_analysis_summary(db, session_id: int) -> None:
    """幂等重建单场 AI 汇总；无报告时仍保留 report_count=0 的可观测记录。"""
    db.query(DeAnchorAiAnalysisSummary).filter(
        DeAnchorAiAnalysisSummary.session_id == session_id
    ).delete()

    session = db.get(LiveSession, session_id)
    if not session:
        return
    room = db.get(LiveRoom, session.room_id) if session.room_id else None
    report_count = db.query(func.count(AnalysisReport.id)).filter(
        AnalysisReport.session_id == session_id
    ).scalar() or 0
    score_report = db.query(AnalysisReport).filter(
        AnalysisReport.session_id == session_id,
        AnalysisReport.report_type == "speech_score",
    ).order_by(AnalysisReport.id.desc()).first()
    content = score_report.report_content if score_report else {}

    db.add(DeAnchorAiAnalysisSummary(
        session_id=session_id,
        anchor_name=session.anchor_name or (room.anchor_name if room else None),
        session_title=session.session_title,
        ai_total_score=_score_value(content, "total_score"),
        completeness_score=_score_value(content, "completeness_score"),
        interactivity_score=_score_value(content, "interactivity_score"),
        lead_guidance_score=_score_value(content, "lead_guidance_score"),
        report_count=report_count,
    ))
