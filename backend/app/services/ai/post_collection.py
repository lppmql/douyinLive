"""采集后处理编排：真实话术 -> AI 复盘 -> 知识库 -> DataEase。"""
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.analysis_reports import AnalysisReport
from app.models.live_sessions import LiveSession
from app.models.transcript_segments import TranscriptSegment
from app.services.ai.kb_service import sync_session_to_kb
from app.services.ai.review_service import generate_findings
from app.services.ai.scoring import score_session_transcript
from app.services.sync import sync_session

logger = logging.getLogger(__name__)


def _run_stage(
    db: Session,
    errors: dict[str, str],
    stage: str,
    operation: Callable[[], Any],
) -> Any:
    try:
        return operation()
    except Exception as exc:
        db.rollback()
        errors[stage] = str(exc)[:500]
        logger.exception("采集后处理阶段失败: stage=%s error=%s", stage, exc)
        return None


def process_session_post_collection(db: Session, session_id: int) -> dict[str, Any]:
    """幂等处理单场直播；复盘或知识库失败时返回可重试状态。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError("直播场次不存在")

    transcript_count = db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id == session_id,
        TranscriptSegment.asr_status == "completed",
    ).count()
    if transcript_count == 0:
        raise ValueError("场次没有已完成的真实话术，暂不能生成复盘")

    errors: dict[str, str] = {}
    existing_score_report = db.query(AnalysisReport).filter(
        AnalysisReport.session_id == session_id,
        AnalysisReport.report_type == "speech_score",
    ).order_by(AnalysisReport.id.desc()).first()
    score = existing_score_report.report_content if existing_score_report else _run_stage(
        db, errors, "speech_score", lambda: score_session_transcript(session_id, db)
    )
    score_report_count = int(existing_score_report is not None or score is not None)
    findings = _run_stage(db, errors, "review", lambda: generate_findings(db, session_id))
    knowledge = _run_stage(db, errors, "knowledge", lambda: sync_session_to_kb(db, session_id))
    dataease = _run_stage(db, errors, "dataease", lambda: (sync_session(db, session_id), True)[1])

    critical_errors = {key: value for key, value in errors.items() if key in {"review", "knowledge"}}
    result = {
        "session_id": session_id,
        "transcript_count": transcript_count,
        "speech_score_status": "completed" if score or score_report_count else "skipped",
        "speech_score": (score or {}).get("total_score") if isinstance(score, dict) else None,
        "review_finding_count": len(findings or []),
        "knowledge": knowledge or {},
        "dataease_synced": dataease is not None,
        "errors": errors,
        "success": not critical_errors,
    }
    logger.info(
        "场次 %s 采集后处理完成: transcript=%s findings=%s knowledge=%s errors=%s",
        session_id,
        transcript_count,
        result["review_finding_count"],
        knowledge,
        errors,
    )
    return result
