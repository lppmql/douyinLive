"""话术评分服务 — 调 DeepSeek 对话术进行多维度评分"""
import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.transcript_segments import TranscriptSegment
from app.models.analysis_reports import AnalysisReport
from app.models.de_tables import DeAnchorTranscriptSummary
from app.services.ai.deepseek_client import chat_json
from app.services.ai.prompt_service import get_prompt

logger = logging.getLogger(__name__)


def score_session_transcript(session_id: int, db: Session | None = None) -> dict[str, Any] | None:
    """对指定场次的话术进行 AI 评分

    流程：
    1. 从 transcript_segments 获取话术内容
    2. 拼接话术文本，按 3000 字分段
    3. 调用 DeepSeek 评分
    4. 保存结果到 analysis_reports 和 de_anchor_transcript_summary
    """
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        # 获取话术
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.session_id == session_id,
            TranscriptSegment.asr_status == "completed",
        ).order_by(TranscriptSegment.segment_start.asc()).all()

        if not segments:
            logger.warning("场次 %d 没有已完成的话术，跳过评分", session_id)
            return None

        # 拼接话术
        full_text = "\n".join([s.text_content or "" for s in segments])
        if len(full_text) < 50:
            logger.warning("场次 %d 话术太短（%d字），跳过评分", session_id, len(full_text))
            return None

        # 获取提示词模板
        prompt = get_prompt(db, "speech_score")
        if not prompt:
            logger.error("未找到 speech_score 提示词模板")
            return None

        # 调用 DeepSeek
        user_message = prompt.replace("{transcript}", full_text[:8000])  # 限制长度
        try:
            result = chat_json(
                system_prompt="你是一个直播话术评分专家。请严格按照要求的JSON格式返回评分结果。",
                user_message=user_message,
                temperature=0.3,
            )
        except Exception as e:
            logger.error("DeepSeek 话术评分失败: %s", e)
            return None

        # 保存评分到 analysis_reports
        report = db.query(AnalysisReport).filter(
            AnalysisReport.session_id == session_id,
            AnalysisReport.report_type == "speech_score",
        ).order_by(AnalysisReport.id.desc()).first()
        if report:
            report.report_title = f"话术评分 - 场次{session_id}"
            report.report_content = result
            report.summary = result.get("total_score", "未知")
        else:
            db.add(AnalysisReport(
                session_id=session_id,
                report_type="speech_score",
                report_title=f"话术评分 - 场次{session_id}",
                report_content=result,
                summary=result.get("total_score", "未知"),
            ))

        # 更新 transcript_segments 的 AI 评分（整体评分）
        total_score = result.get("total_score")
        if total_score is not None:
            avg_score = float(total_score)
            for seg in segments:
                seg.ai_score = Decimal(str(avg_score))

        # 更新 de_anchor_transcript_summary
        summary = db.query(DeAnchorTranscriptSummary).filter(
            DeAnchorTranscriptSummary.session_id == session_id
        ).first()
        if summary:
            summary.avg_ai_score = float(total_score) if total_score else None

        db.commit()
        logger.info("场次 %d 话术评分完成: total=%s", session_id, total_score)
        return result

    except Exception as e:
        logger.exception("话术评分异常: %s", e)
        db.rollback()
        return None
    finally:
        if should_close:
            db.close()


def batch_score_recent(db: Session, limit: int = 10) -> list[int]:
    """批量评分最近 limit 场有话术但未评分的场次"""
    from app.models.live_sessions import LiveSession

    scored_ids = db.query(AnalysisReport.session_id).filter(
        AnalysisReport.report_type == "speech_score"
    ).subquery()

    sessions = db.query(LiveSession).filter(
        LiveSession.id.notin_(scored_ids),
        LiveSession.live_status == "ended",
    ).order_by(LiveSession.live_end_time.desc()).limit(limit).all()

    scored = []
    for s in sessions:
        if score_session_transcript(s.id, db):
            scored.append(s.id)
    return scored
