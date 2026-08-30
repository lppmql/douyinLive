"""采集控制中心的一次性批处理执行器。

每个执行器只负责一个业务边界：真实数据刷新、AI 复盘、知识库或剪辑。
任务状态、停止和重试由 control.py 统一管理，避免每个模块各写一套队列逻辑。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session

from app.models.analysis_reports import AnalysisReport
from app.models.asr_tasks import AsrTask
from app.models.comments import Comment
from app.models.knowledge_base import KnowledgeBase
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.live_sessions import LiveSession
from app.models.review import ReviewFinding
from app.models.scraper_tasks import ScraperTask
from app.models.transcript_segments import TranscriptSegment
from app.services.ai.kb_service import sync_session_to_kb
from app.services.ai.review_service import generate_findings
from app.services.ai.scoring import score_session_transcript
from app.services.collector.log_service import add_collector_log
from app.services.collector.manual_collect import collect_all
from app.services.collector.comment_profile_enrichment import (
    comment_profile_enrichment_manager,
    profile_configuration_status,
)
from app.services.clips.clip_service import (
    generate_and_render_session,
    pending_clip_session_ids,
    rerender_clip_subtitles,
)
from app.services.tasks.exceptions import TaskBatchFailed, TaskCancellationRequested


ProgressReporter = Callable[[str, int, int, int, str, dict[str, Any] | None], None]
CancellationChecker = Callable[[], bool]


def completed_offline_transcript_exists():
    """只有成功完成的下播终稿，才能进入 AI 复盘和知识库。"""
    return exists().where(
        and_(
            AsrTask.session_id == LiveSession.id,
            AsrTask.task_type == "offline",
            AsrTask.status == "completed",
        )
    )


def _ensure_running(should_cancel: CancellationChecker) -> None:
    if should_cancel():
        raise TaskCancellationRequested("用户已停止任务")


async def run_data_refresh(
    db: Session,
    task_id: int,
    report: ProgressReporter,
    should_cancel: CancellationChecker,
) -> dict[str, Any]:
    """只刷新采集数据，不再隐式触发 ASR、AI 或知识库。"""
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
    # 每次真实数据刷新后自动低速补齐新增评论用户。服务自身负责缓存、退避、
    # 单并发和平台风控；未配置独立 Cookie 时静默跳过，不阻断主采集任务。
    profile_enrichment_started = False
    if profile_configuration_status()["configured"]:
        try:
            comment_profile_enrichment_manager.start(session_id=None, force=False)
            profile_enrichment_started = True
        except RuntimeError:
            pass
    result["profile_enrichment_started"] = profile_enrichment_started
    return result


def _pending_ai_session_ids(db: Session, limit: int | None = None) -> list[int]:
    query = _pending_ai_query(db).order_by(
        LiveSession.live_start_time.desc(),
        LiveSession.id.desc(),
    )
    if limit is not None:
        query = query.limit(max(1, limit))
    return [row[0] for row in query.all()]


def _pending_ai_query(db: Session):
    """AI 状态数量和实际候选共用同一套“下播终稿”门禁。"""
    has_offline_transcript = exists().where(
        TranscriptSegment.session_id == LiveSession.id,
        TranscriptSegment.asr_status == "completed",
        or_(
            TranscriptSegment.segment_type.is_(None),
            TranscriptSegment.segment_type == "asr_offline",
        ),
    )
    has_score = exists().where(
        AnalysisReport.session_id == LiveSession.id,
        AnalysisReport.report_type == "speech_score",
    )
    has_finding = exists().where(ReviewFinding.session_id == LiveSession.id)
    return db.query(LiveSession.id).filter(
        LiveSession.live_status != "live",
        completed_offline_transcript_exists(),
        has_offline_transcript,
        or_(~has_score, ~has_finding),
    )


def pending_ai_session_count(db: Session) -> int:
    """返回已有离线终稿但尚未补齐 AI 复盘的真实场次数。"""
    return int(
        _pending_ai_query(db)
        .order_by(None)
        .with_entities(func.count(LiveSession.id))
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
    report(
        "ai_review",
        0,
        0,
        total,
        f"发现 {total} 场待生成 AI 复盘",
        {"pending_count": total},
    )

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
                "anchor_name": session.anchor_name or session.anchor_nickname
                if session
                else None,
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
            LiveSession.detail_collection_status == "complete",
            LiveSession.live_status != "live",
            completed_offline_transcript_exists(),
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
    return int(
        query.order_by(None).with_entities(func.count(LiveSession.id)).scalar() or 0
    )


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
    report(
        "knowledge_sync",
        0,
        0,
        total,
        f"发现 {total} 场知识需要更新",
        {"pending_count": total},
    )

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
                if key.endswith("_saved")
                or key in {"time_slices_created", "time_slices_updated"}
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
                "anchor_name": session.anchor_name or session.anchor_nickname
                if session
                else None,
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


def run_clip_batch(
    db: Session,
    task_id: int,
    report: ProgressReporter,
    should_cancel: CancellationChecker,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """AI 自动剪辑任务执行器。

    任务参数（task_options_json）：
    - session_id: 指定场次（自动触发或手动触发都带）；
    - clip_order: 手动重剪时替换的成片序号（可选）；
    - user_hint: 人工指定的主题/时间范围要求（可选）；
    未指定 session_id 时为历史场次补生成模式（只处理还没有成片的场次）。
    """
    task = db.get(ScraperTask, task_id)
    options = dict(task.task_options_json or {}) if task else {}
    from app.services.clips.storage_retention import prune_replay_storage

    storage_cleanup = prune_replay_storage(db)

    if options.get("operation") == "subtitle_rerender":
        clip_id = int(options.get("clip_id") or 0)
        if clip_id <= 0:
            raise TaskBatchFailed("字幕重制任务缺少成片 ID", {"clip_id": clip_id})
        _ensure_running(should_cancel)
        report(
            "subtitle_rerender",
            10,
            0,
            1,
            "正在复用无字幕底片重制字幕",
            {"clip_id": clip_id},
        )
        record = rerender_clip_subtitles(
            db,
            clip_id,
            requested_segments=options.get("segments"),
            target_render_version=int(options.get("target_render_version") or 0)
            or None,
        )
        result = {
            "session_id": record.session_id,
            "clip_id": record.id,
            "render_version": record.render_version,
            "subtitle_precision": record.subtitle_precision,
            "rendered_count": 1,
            "failed_count": 0,
            "storage_cleanup": storage_cleanup,
        }
        report(
            "subtitle_rerender",
            99,
            1,
            1,
            f"字幕重制完成，当前版本 v{record.render_version}",
            result,
        )
        return result

    specified = options.get("session_ids") or (options.get("session_id"),)
    if specified:
        session_ids = [int(s) for s in specified if s is not None]
    else:
        session_ids = pending_clip_session_ids(db, limit=batch_size)

    total = len(session_ids)
    completed = 0
    failed = 0
    rendered_total = 0
    selected_clip_total = 0
    failed_clip_total = 0
    warning_total = 0
    subtitle_alignment_warning_total = 0
    errors: list[dict[str, Any]] = []
    report("clip", 0, 0, total, f"发现 {total} 场待剪辑", {"pending_count": total})

    for index, session_id in enumerate(session_ids, start=1):
        _ensure_running(should_cancel)
        session = db.get(LiveSession, session_id)
        if not session:
            failed += 1
            errors.append({"session_id": session_id, "message": "场次不存在"})
            continue
        try:
            result = generate_and_render_session(
                db,
                session_id,
                task_id=task_id,
                report=report,
                should_cancel=should_cancel,
                user_hint=options.get("user_hint"),
                clip_order=int(options["clip_order"])
                if options.get("clip_order")
                else None,
            )
            rendered_count = int(result.get("rendered_count") or 0)
            selected_clip_count = int(result.get("selected_count") or 0)
            failed_clip_count = int(result.get("failed_count") or 0)
            alignment_warning_count = int(
                result.get("subtitle_alignment_warning_count") or 0
            )
            selected_clip_total += selected_clip_count
            rendered_total += rendered_count
            failed_clip_total += failed_clip_count
            subtitle_alignment_warning_total += alignment_warning_count
            has_warning = failed_clip_count > 0 or alignment_warning_count > 0
            if not clip_session_render_succeeded(result):
                failed += 1
                message = (
                    f"AI 已选出 {selected_clip_count} 条候选，但没有任何成片渲染成功"
                )
                errors.append({"session_id": session_id, "message": message})
                add_collector_log(
                    db,
                    task_id=task_id,
                    session=session,
                    level="error",
                    stage="clip",
                    event_type="session_clip_failed",
                    message=f"场次 #{session_id} AI 剪辑失败：{message}",
                    details=result,
                )
                db.commit()
            else:
                completed += 1
                warning_total += int(has_warning)
                add_collector_log(
                    db,
                    task_id=task_id,
                    session=session,
                    level="warning" if has_warning else "info",
                    stage="clip",
                    event_type=(
                        "session_clip_completed_with_warnings"
                        if has_warning
                        else "session_clip_completed"
                    ),
                    message=(
                        f"主播 {session.anchor_name or session.anchor_nickname or '未知主播'}，"
                        f"场次 #{session.id} AI 剪辑完成，成功 {rendered_count} 条，"
                        f"成片失败 {failed_clip_count} 条，字幕降级 {alignment_warning_count} 段"
                    ),
                    details=result,
                )
                db.commit()
        except TaskCancellationRequested:
            # 用户取消/安全关机：交给 control.py 统一标记 CANCELLED，不记失败
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            failed += 1
            errors.append({"session_id": session_id, "message": str(exc)[:300]})
            add_collector_log(
                db,
                task_id=task_id,
                session=session,
                level="error",
                stage="clip",
                event_type="session_clip_failed",
                message=f"场次 #{session_id} AI 剪辑失败：{str(exc)[:300]}",
                details={"error": str(exc)[:500]},
            )
            db.commit()

        report(
            "clip",
            int(index / max(total, 1) * 99),
            index,
            total,
            f"剪辑已处理 {index}/{total} 场，成功 {completed} 场，失败 {failed} 场",
            {
                "session_id": session_id,
                "anchor_name": session.anchor_name or session.anchor_nickname
                if session
                else None,
                "completed_count": completed,
                "failed_count": failed,
                "rendered_count": rendered_total,
                "failed_clip_count": failed_clip_total,
                "warning_count": warning_total,
            },
        )

    result = {
        "selected_count": total,
        "completed_count": completed,
        "failed_count": failed,
        "rendered_count": rendered_total,
        "selected_clip_count": selected_clip_total,
        "failed_clip_count": failed_clip_total,
        "warning_count": warning_total,
        "subtitle_alignment_warning_count": subtitle_alignment_warning_total,
        "errors": errors[:20],
        "storage_cleanup": storage_cleanup,
    }
    if total and completed == 0:
        raise TaskBatchFailed("待处理场次的 AI 剪辑全部失败", result)
    return result


def clip_session_render_succeeded(result: dict[str, Any]) -> bool:
    """只有至少一条真实成片完成渲染，场次级剪辑才算成功。"""
    return int(result.get("rendered_count") or 0) > 0
