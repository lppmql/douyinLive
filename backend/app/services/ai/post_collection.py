"""采集后处理编排：真实话术 -> AI 复盘 -> 知识库 -> DataEase -> AI 自动剪辑。"""

import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger as core_logger
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.models.transcript_segments import TranscriptSegment
from app.services.ai.kb_service import sync_session_to_kb
from app.services.ai.review_service import generate_findings
from app.services.ai.scoring import score_session_transcript
from app.services.ai.unified_review import generate_unified_review
from app.services.sync import sync_session

logger = logging.getLogger(__name__)


def _queue_clip_automatically(session_id: int) -> None:
    """离线终稿完成后自动排队 AI 剪辑（仅当场次有回放流源，且开关开启）。"""
    if not settings.CLIP_AUTO_GENERATE:
        return
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        has_source = (
            db.query(StreamSource.id)
            .filter(StreamSource.session_id == session_id)
            .first()
            is not None
        )
        if not has_source:
            logger.info("场次 %s 无回放流源，跳过自动剪辑", session_id)
            return
        from app.services.tasks.control import collector_task_control

        task, created = collector_task_control.enqueue(
            "clip", {"session_id": session_id}
        )
        if created:
            core_logger.info(
                "离线终稿完成，自动排队 AI 剪辑 session=%s task=%s", session_id, task.id
            )
    except Exception as exc:  # noqa: BLE001 - 自动剪辑失败不应阻断主后处理链
        logger.warning("自动排队 AI 剪辑失败 session=%s: %s", session_id, exc)
    finally:
        db.close()


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

    transcript_count = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.session_id == session_id,
            TranscriptSegment.asr_status == "completed",
        )
        .count()
    )
    if transcript_count == 0:
        raise ValueError("场次没有已完成的真实话术，暂不能生成复盘")

    errors: dict[str, str] = {}
    # 最终稿可能替换直播初稿。评分服务会更新已有 speech_score 报告，
    # 因此每次终稿后处理都要重算，不能复用初稿时代的旧分数。
    score = _run_stage(
        db,
        errors,
        "speech_score",
        lambda: score_session_transcript(session_id, db),
    )
    findings = _run_stage(
        db, errors, "review", lambda: generate_findings(db, session_id)
    )
    unified_review = _run_stage(
        db, errors, "unified_review", lambda: generate_unified_review(db, session_id)
    )
    knowledge = _run_stage(
        db, errors, "knowledge", lambda: sync_session_to_kb(db, session_id)
    )
    dataease = _run_stage(
        db, errors, "dataease", lambda: (sync_session(db, session_id), True)[1]
    )

    critical_errors = {
        key: value for key, value in errors.items() if key in {"review", "knowledge"}
    }
    result = {
        "session_id": session_id,
        "transcript_count": transcript_count,
        "speech_score_status": "completed" if score else "skipped",
        "speech_score": (score or {}).get("total_score")
        if isinstance(score, dict)
        else None,
        "review_finding_count": len(findings or []),
        "audience_analysis_count": int(
            (unified_review or {}).get("analyzed_user_count", 0)
        ),
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
    # 后处理链全部完成（或至少复盘与知识库成功）后，自动触发 AI 剪辑。
    if not critical_errors:
        _queue_clip_automatically(session_id)
    return result
