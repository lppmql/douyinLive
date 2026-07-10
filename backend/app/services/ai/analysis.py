"""趋势分析 + 异常检测服务"""
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.live_sessions import LiveSession
from app.models.analysis_reports import AnalysisReport
from app.models.de_tables import DeAnchorConversionFunnel
from app.services.ai.deepseek_client import chat_json
from app.services.ai.prompt_service import get_prompt

logger = logging.getLogger(__name__)


def _format_session_for_ai(session: LiveSession) -> dict:
    """将场次数据格式化为 AI 友好的字典"""
    return {
        "id": session.id,
        "title": session.session_title or "",
        "anchor": session.room.anchor_name if session.room else "",
        "start_time": str(session.live_start_time or ""),
        "end_time": str(session.live_end_time or ""),
        "duration_minutes": session.live_duration_seconds // 60 if session.live_duration_seconds else 0,
        "total_viewers": session.total_viewers or 0,
        "leads_count": session.leads_count or 0,
        "peak_online": session.peak_online_count or 0,
        "new_followers": session.new_followers or 0,
        "comments_count": session.comments_count or 0,
        "ad_cost": float(session.ad_cost) if session.ad_cost else 0,
        "avg_watch_seconds": float(session.avg_watch_seconds) if session.avg_watch_seconds else 0,
    }


def analyze_trend(session_ids: list[int], db: Session | None = None) -> dict[str, Any] | None:
    """趋势分析：对比多场直播数据"""
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        sessions = db.query(LiveSession).filter(
            LiveSession.id.in_(session_ids),
            LiveSession.live_status == "ended",
        ).order_by(LiveSession.live_start_time.asc()).all()

        if len(sessions) < 2:
            logger.warning("需要至少 2 场直播才能做趋势分析")
            return None

        sessions_data = json.dumps(
            [_format_session_for_ai(s) for s in sessions],
            ensure_ascii=False, indent=2,
        )

        prompt = get_prompt(db, "trend_analysis")
        if not prompt:
            return None

        result = chat_json(
            system_prompt="你是一个直播数据分析师。请按要求输出 JSON。",
            user_message=prompt.replace("{sessions_data}", sessions_data),
            temperature=0.3,
        )

        # 保存报告
        report = AnalysisReport(
            session_id=sessions[-1].id,  # 关联最后一期
            report_type="trend",
            report_title=f"趋势分析 - {len(sessions)}场对比",
            report_content=result,
            summary=result.get("summary", ""),
        )
        db.add(report)
        db.commit()

        return result
    except Exception as e:
        logger.exception("趋势分析失败: %s", e)
        db.rollback()
        return None
    finally:
        if should_close:
            db.close()


def detect_anomalies(session_id: int, db: Session | None = None) -> dict[str, Any] | None:
    """异常检测：分析单场直播的异常情况"""
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        session = db.query(LiveSession).filter(LiveSession.id == session_id).first()
        if not session:
            return None

        # 获取历史数据（最近10场已结束）
        history = db.query(LiveSession).filter(
            LiveSession.id != session_id,
            LiveSession.live_status == "ended",
        ).order_by(LiveSession.live_start_time.desc()).limit(10).all()

        prompt = get_prompt(db, "anomaly_detection")
        if not prompt:
            return None

        user_message = prompt.replace(
            "{session_data}", json.dumps(_format_session_for_ai(session), ensure_ascii=False)
        ).replace(
            "{history_data}", json.dumps(
                [_format_session_for_ai(s) for s in history], ensure_ascii=False, indent=2,
            )
        )

        result = chat_json(
            system_prompt="你是一个异常检测分析师。请按要求输出 JSON。",
            user_message=user_message,
            temperature=0.3,
        )

        report = AnalysisReport(
            session_id=session_id,
            report_type="anomaly",
            report_title=f"异常检测 - 场次{session_id}",
            report_content=result,
            summary=json.dumps(result.get("anomalies", []), ensure_ascii=False),
        )
        db.add(report)
        db.commit()

        return result
    except Exception as e:
        logger.exception("异常检测失败: %s", e)
        db.rollback()
        return None
    finally:
        if should_close:
            db.close()
