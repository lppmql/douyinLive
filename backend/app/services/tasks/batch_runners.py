"""采集控制中心的一次性批处理执行器。

每个执行器只负责一个业务边界：真实数据刷新、AI 复盘、知识库或 DataEase。
任务状态、停止和重试由 control.py 统一管理，避免每个模块各写一套队列逻辑。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import case, exists, func, or_
from sqlalchemy.orm import Session

from app.models.analysis_reports import AnalysisReport
from app.models.comments import Comment
from app.models.knowledge_base import KnowledgeBase
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.live_sessions import LiveSession
from app.models.review import ReviewFinding
from app.models.transcript_segments import TranscriptSegment
from app.services.ai.kb_service import sync_session_to_kb
from app.services.ai.review_service import generate_findings
from app.services.ai.scoring import score_session_transcript
from app.services.collector.log_service import add_collector_log
from app.services.collector.manual_collect import collect_all
from app.services.sync.de_sync import cleanup_stale_dataease_rows, pending_complete_session_ids, sync_session
from app.services.tasks.exceptions import TaskBatchFailed, TaskCancellationRequested


ProgressReporter = Callable[[str, int, int, int, str, dict[str, Any] | None], None]
CancellationChecker = Callable[[], bool]


def _ensure_running(should_cancel: CancellationChecker) -> None:
    if should_cancel():
        raise TaskCancellationRequested("用户已停止任务")


async def run_data_refresh(
    db: Session,
    task_id: int,
    report: ProgressReporter,
    should_cancel: CancellationChecker,
) -> dict[str, Any]:
    """只刷新采集数据，不再隐式触发 ASR、AI、知识库或 DataEase。"""
    result = await collect_all(
        db,
        task_id=task_id,
        progress_callback=report,
        cancellation_callback=should_cancel,
    )
    succeeded = any(
        int(result.get(key) or 0) > 0
        for key in (
            "collected_rooms",
            "enterprise_anchor_count",
            "enterprise_session_discovered_count",
            "history_detail_checked_count",
        )
    )
    if not succeeded:
        raise TaskBatchFailed(result.get("message") or "没有采集到可用真实数据", result)
    return result


def _pending_ai_session_ids(db: Session, limit: int | None = None) -> list[int]:
    transcript_ids = {
        row[0]
        for row in db.query(TranscriptSegment.session_id)
        .filter(TranscriptSegment.asr_status == "completed")
        .distinct()
        .all()
    }
    if not transcript_ids:
        return []
    scored_ids = {
        row[0]
        for row in db.query(AnalysisReport.session_id)
        .filter(
            AnalysisReport.session_id.in_(transcript_ids),
            AnalysisReport.report_type == "speech_score",
        )
        .distinct()
        .all()
    }
    finding_ids = {
        row[0]
        for row in db.query(ReviewFinding.session_id)
        .filter(ReviewFinding.session_id.in_(transcript_ids))
        .distinct()
        .all()
    }
    pending = transcript_ids - (scored_ids & finding_ids)
    if not pending:
        return []
    query = (
        db.query(LiveSession.id)
        .filter(LiveSession.id.in_(pending))
        .order_by(
            case((LiveSession.live_status == "live", 0), else_=1),
            LiveSession.live_start_time.desc(),
            LiveSession.id.desc(),
        )
    )
    if limit is not None:
        query = query.limit(max(1, limit))
    return [row[0] for row in query.all()]


def pending_ai_session_count(db: Session) -> int:
    """返回已有话术但尚未补齐 AI 复盘的真实场次数。"""
    has_transcript = exists().where(
        TranscriptSegment.session_id == LiveSession.id,
        TranscriptSegment.asr_status == "completed",
    )
    has_score = exists().where(
        AnalysisReport.session_id == LiveSession.id,
        AnalysisReport.report_type == "speech_score",
    )
    has_finding = exists().where(ReviewFinding.session_id == LiveSession.id)
    return int(
        db.query(func.count(LiveSession.id))
        .filter(has_transcript, or_(~has_score, ~has_finding))
        .scalar()
        or 0
    )


def run_ai_review_batch(
    db: Session,
    task_id: int,
    report: ProgressReporter,
    should_cancel: CancellationChecker,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """为已有真实话术但缺少复盘结果的场次补齐 AI 评分和证据发现。"""
    session_ids = _pending_ai_session_ids(db, limit=batch_size)
    total = len(session_ids)
    completed = 0
    failed = 0
    warnings = 0
    errors: list[dict[str, Any]] = []
    report("ai_review", 0, 0, total, f"发现 {total} 场待生成 AI 复盘", {"pending_count": total})

    for index, session_id in enumerate(session_ids, start=1):
        _ensure_running(should_cancel)
        session = db.get(LiveSession, session_id)
        if not session:
            continue
        stage_errors: list[str] = []
        try:
            score_report = (
                db.query(AnalysisReport)
                .filter(
                    AnalysisReport.session_id == session_id,
                    AnalysisReport.report_type == "speech_score",
                )
                .order_by(AnalysisReport.id.desc())
                .first()
            )
            if not score_report:
                try:
                    score_session_transcript(session_id, db)
                except Exception as exc:
                    db.rollback()
                    stage_errors.append(f"话术评分：{str(exc)[:300]}")
            findings = generate_findings(db, session_id)
            completed += 1
            warnings += int(bool(stage_errors))
            add_collector_log(
                db,
                task_id=task_id,
                session=session,
                level="warn" if stage_errors else "info",
                stage="ai_review",
                event_type="session_reviewed",
                message=(
                    f"主播 {session.anchor_name or session.anchor_nickname or '未知主播'}，"
                    f"场次 #{session.id} AI 复盘完成，共生成 {len(findings)} 条证据发现"
                ),
                details={
                    "finding_count": len(findings),
                    "score_generated": not bool(score_report),
                    "warnings": stage_errors,
                },
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            failed += 1
            errors.append({"session_id": session_id, "message": str(exc)[:300]})
            session = db.get(LiveSession, session_id)
            add_collector_log(
                db,
                task_id=task_id,
                session=session,
                level="error",
                stage="ai_review",
                event_type="session_review_failed",
                message=f"场次 #{session_id} AI 复盘失败：{str(exc)[:300]}",
                details={"error": str(exc)[:500]},
            )
            db.commit()

        report(
            "ai_review",
            int(index / max(total, 1) * 99),
            index,
            total,
            f"AI 复盘已处理 {index}/{total} 场，成功 {completed} 场，失败 {failed} 场",
            {
                "session_id": session_id,
                "anchor_name": session.anchor_name or session.anchor_nickname if session else None,
                "completed_count": completed,
                "failed_count": failed,
                "warning_count": warnings,
            },
        )

    result = {
        "selected_count": total,
        "completed_count": completed,
        "failed_count": failed,
        "warning_count": warnings,
        "errors": errors[:20],
    }
    if total and completed == 0:
        raise TaskBatchFailed("待处理场次的 AI 复盘全部失败", result)
    return result


def _pending_knowledge_query(db: Session):
    """集中维护知识库增量条件，列表和数量不会因两份逻辑而偏差。"""
    latest_kb = (
        db.query(
            KnowledgeBase.session_id.label("session_id"),
            func.max(KnowledgeBase.updated_at).label("latest_updated_at"),
        )
        .filter(KnowledgeBase.session_id.isnot(None))
        .group_by(KnowledgeBase.session_id)
        .subquery()
    )
    return (
        db.query(LiveSession.id)
        .outerjoin(latest_kb, latest_kb.c.session_id == LiveSession.id)
        .filter(
            or_(LiveSession.detail_collection_status == "complete", LiveSession.live_status == "live"),
            or_(
                latest_kb.c.session_id.is_(None),
                LiveSession.updated_at > latest_kb.c.latest_updated_at,
                exists().where(
                    Comment.session_id == LiveSession.id,
                    Comment.updated_at > latest_kb.c.latest_updated_at,
                ),
                exists().where(
                    LiveMetric.session_id == LiveSession.id,
                    LiveMetric.updated_at > latest_kb.c.latest_updated_at,
                ),
                exists().where(
                    LiveAudienceProfile.session_id == LiveSession.id,
                    LiveAudienceProfile.updated_at > latest_kb.c.latest_updated_at,
                ),
                exists().where(
                    TranscriptSegment.session_id == LiveSession.id,
                    TranscriptSegment.updated_at > latest_kb.c.latest_updated_at,
                ),
                exists().where(
                    AnalysisReport.session_id == LiveSession.id,
                    AnalysisReport.updated_at > latest_kb.c.latest_updated_at,
                ),
                exists().where(
                    ReviewFinding.session_id == LiveSession.id,
                    ReviewFinding.updated_at > latest_kb.c.latest_updated_at,
                ),
            ),
        )
    )


def _pending_knowledge_session_ids(db: Session, limit: int | None = None) -> list[int]:
    query = _pending_knowledge_query(db).order_by(
        case((LiveSession.live_status == "live", 0), else_=1),
        LiveSession.live_start_time.desc(),
        LiveSession.id.desc(),
    )
    if limit is not None:
        query = query.limit(max(1, limit))
    return [row[0] for row in query.all()]


def pending_knowledge_session_count(db: Session) -> int:
    """返回源数据有更新、需要重新写入知识库的场次数。"""
    query = _pending_knowledge_query(db)
    return int(query.order_by(None).with_entities(func.count(LiveSession.id)).scalar() or 0)


def run_knowledge_sync_batch(
    db: Session,
    task_id: int,
    report: ProgressReporter,
    should_cancel: CancellationChecker,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """增量同步有新数据的完整场次，避免每次重复扫描全部知识。"""
    session_ids = _pending_knowledge_session_ids(db, limit=batch_size)
    total = len(session_ids)
    completed = 0
    failed = 0
    saved_items = 0
    errors: list[dict[str, Any]] = []
    report("knowledge_sync", 0, 0, total, f"发现 {total} 场知识需要更新", {"pending_count": total})

    for index, session_id in enumerate(session_ids, start=1):
        _ensure_running(should_cancel)
        session = db.get(LiveSession, session_id)
        if not session:
            continue
        try:
            result = sync_session_to_kb(db, session_id)
            changed = sum(
                int(value or 0)
                for key, value in result.items()
                if key.endswith("_saved") or key in {"time_slices_created", "time_slices_updated"}
            )
            saved_items += changed
            completed += 1
            add_collector_log(
                db,
                task_id=task_id,
                session=session,
                level="info",
                stage="knowledge_sync",
                event_type="session_knowledge_synced",
                message=(
                    f"主播 {session.anchor_name or session.anchor_nickname or '未知主播'}，"
                    f"场次 #{session.id} 已存入知识库，本次更新 {changed} 项"
                ),
                details=result,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            failed += 1
            errors.append({"session_id": session_id, "message": str(exc)[:300]})
            session = db.get(LiveSession, session_id)
            add_collector_log(
                db,
                task_id=task_id,
                session=session,
                level="error",
                stage="knowledge_sync",
                event_type="session_knowledge_failed",
                message=f"场次 #{session_id} 存入知识库失败：{str(exc)[:300]}",
                details={"error": str(exc)[:500]},
            )
            db.commit()

        report(
            "knowledge_sync",
            int(index / max(total, 1) * 99),
            index,
            total,
            f"知识库已处理 {index}/{total} 场，成功 {completed} 场，失败 {failed} 场",
            {
                "session_id": session_id,
                "anchor_name": session.anchor_name or session.anchor_nickname if session else None,
                "completed_count": completed,
                "failed_count": failed,
                "saved_item_count": saved_items,
            },
        )

    result = {
        "selected_count": total,
        "completed_count": completed,
        "failed_count": failed,
        "saved_item_count": saved_items,
        "errors": errors[:20],
    }
    if total and completed == 0:
        raise TaskBatchFailed("待处理场次全部未能存入知识库", result)
    return result


def run_dataease_sync_batch(
    db: Session,
    task_id: int,
    report: ProgressReporter,
    should_cancel: CancellationChecker,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """逐场同步全部缺失或过期的 DataEase 数据，支持中途安全停止。"""
    removed = cleanup_stale_dataease_rows(db)
    session_ids = pending_complete_session_ids(
        db,
        limit=batch_size,
        force=False,
        include_live=True,
    )
    total = len(session_ids)
    completed = 0
    failed = 0
    errors: list[dict[str, Any]] = []
    report(
        "dataease_sync",
        0,
        0,
        total,
        f"发现 {total} 场 DataEase 数据需要同步",
        {"pending_count": total, "removed_stale_row_count": removed},
    )

    for index, session_id in enumerate(session_ids, start=1):
        _ensure_running(should_cancel)
        session = db.get(LiveSession, session_id)
        if not session:
            continue
        try:
            sync_session(db, session_id)
            completed += 1
            add_collector_log(
                db,
                task_id=task_id,
                session=session,
                level="info",
                stage="dataease_sync",
                event_type="session_dataease_synced",
                message=(
                    f"主播 {session.anchor_name or session.anchor_nickname or '未知主播'}，"
                    f"场次 #{session.id} 已同步到 DataEase 数据库"
                ),
                details={"synced_count": 1},
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            failed += 1
            errors.append({"session_id": session_id, "message": str(exc)[:300]})
            session = db.get(LiveSession, session_id)
            add_collector_log(
                db,
                task_id=task_id,
                session=session,
                level="error",
                stage="dataease_sync",
                event_type="session_dataease_failed",
                message=f"场次 #{session_id} 同步 DataEase 失败：{str(exc)[:300]}",
                details={"error": str(exc)[:500]},
            )
            db.commit()

        report(
            "dataease_sync",
            int(index / max(total, 1) * 99),
            index,
            total,
            f"DataEase 已同步 {index}/{total} 场，成功 {completed} 场，失败 {failed} 场",
            {
                "session_id": session_id,
                "anchor_name": session.anchor_name or session.anchor_nickname if session else None,
                "completed_count": completed,
                "failed_count": failed,
                "removed_stale_row_count": removed,
            },
        )

    result = {
        "selected_count": total,
        "synced_count": completed,
        "failed_count": failed,
        "removed_stale_row_count": removed,
        "errors": errors[:20],
    }
    if total and completed == 0:
        raise TaskBatchFailed("待处理场次全部同步 DataEase 失败", result)
    return result
