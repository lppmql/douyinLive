"""统一任务队列的只读视图适配。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.status import TaskStatus
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.asr_tasks import AsrTask
from app.models.live_sessions import LiveSession
from app.models.scraper_tasks import ScraperTask
from app.services.tasks.control import CONTROL_TASK_TYPES, TASK_LABELS, TASK_TYPE_MODULES


ACTIVE_STATUSES = {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.PROCESSING}


def serialize_scraper_task(task: ScraperTask) -> dict[str, Any]:
    status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status or TaskStatus.FAILED.value)
    return {
        "task_key": f"scraper:{task.id}",
        "source": "scraper",
        "id": task.id,
        "module_key": TASK_TYPE_MODULES.get(task.task_type, "data_refresh"),
        "task_type": task.task_type,
        "task_label": TASK_LABELS.get(task.task_type, task.task_type),
        "status": status,
        "progress_percent": int(task.progress_percent or 0),
        "progress_current": int(task.progress_current or 0),
        "progress_total": int(task.progress_total or 0),
        "progress_stage": task.progress_stage,
        "progress_message": task.progress_message,
        "account_id": task.account_id,
        "session_id": task.session_id,
        "anchor_name": None,
        "anchor_nickname": None,
        "anchor_avatar_url": None,
        "douyin_id": None,
        "session_title": None,
        "error_message": task.error_message,
        "trace_id": task.trace_id,
        "worker_id": task.worker_id,
        "heartbeat_at": task.heartbeat_at,
        "retry_count": int(task.retry_count or 0),
        "max_retries": int(task.max_retries or 0),
        "retry_of_task_id": task.retry_of_task_id,
        "can_stop": status in {TaskStatus.PENDING, TaskStatus.RUNNING},
        "can_retry": status in {TaskStatus.FAILED, TaskStatus.CANCELLED},
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "result_json": task.result_json,
        "collected_anchor_count": int(task.collected_anchor_count or 0),
        "collected_session_count": int(task.collected_session_count or 0),
        "new_session_count": int(task.new_session_count or 0),
        "checked_detail_count": int(task.checked_detail_count or 0),
        "refreshed_detail_count": int(task.refreshed_detail_count or 0),
        "failed_detail_count": int(task.failed_detail_count or 0),
        "remaining_detail_count": int(task.remaining_detail_count or 0),
    }


def _asr_chunk_counts(db: Session, task_ids: list[int]) -> dict[int, tuple[int, int]]:
    counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    if not task_ids:
        return {}
    rows = (
        db.query(AsrAudioChunk.task_id, AsrAudioChunk.status, func.count(AsrAudioChunk.id))
        .filter(AsrAudioChunk.task_id.in_(task_ids))
        .group_by(AsrAudioChunk.task_id, AsrAudioChunk.status)
        .all()
    )
    for task_id, status, count in rows:
        counts[task_id][0] += int(count or 0)
        if status == TaskStatus.COMPLETED:
            counts[task_id][1] += int(count or 0)
    return {task_id: (values[0], values[1]) for task_id, values in counts.items()}


def serialize_asr_task(
    task: AsrTask,
    session: LiveSession,
    chunk_counts: tuple[int, int] = (0, 0),
) -> dict[str, Any]:
    total, completed = chunk_counts
    status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status or TaskStatus.FAILED.value)
    percentage = 100 if status == TaskStatus.COMPLETED else int(completed / total * 100) if total else 0
    message = (
        f"正在转写音频分片 {completed + 1}/{total}"
        if status == TaskStatus.PROCESSING and total
        else f"已完成 {completed}/{total} 个音频分片"
        if total
        else "等待分析真实直播音频"
    )
    return {
        "task_key": f"asr:{task.id}",
        "source": "asr",
        "id": task.id,
        "module_key": "asr",
        "task_type": "asr_transcription",
        "task_label": "ASR 话术转写",
        "status": status,
        "progress_percent": percentage,
        "progress_current": completed,
        "progress_total": total,
        "progress_stage": "asr_transcription",
        "progress_message": message,
        "account_id": None,
        "session_id": task.session_id,
        "anchor_name": session.anchor_name or session.anchor_nickname,
        "anchor_nickname": session.anchor_nickname,
        "anchor_avatar_url": session.anchor_avatar_url,
        "douyin_id": session.douyin_id,
        "session_title": session.session_title,
        "error_message": task.error_message,
        "trace_id": task.trace_id,
        "worker_id": task.worker_id,
        "heartbeat_at": task.heartbeat_at,
        "retry_count": int(task.retry_count or 0),
        "max_retries": int(task.max_retries or 0),
        "retry_of_task_id": None,
        "can_stop": status in {TaskStatus.QUEUED, TaskStatus.PROCESSING},
        "can_retry": status in {TaskStatus.FAILED, TaskStatus.CANCELLED},
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "result_json": task.postprocess_result,
        "collected_anchor_count": 0,
        "collected_session_count": 0,
        "new_session_count": 0,
        "checked_detail_count": 0,
        "refreshed_detail_count": 0,
        "failed_detail_count": 0,
        "remaining_detail_count": 0,
    }


def list_unified_tasks(db: Session, limit: int = 100) -> list[dict[str, Any]]:
    """合并控制任务和逐场 ASR 任务，按创建时间统一排序。"""
    scraper_tasks = (
        db.query(ScraperTask)
        .filter(ScraperTask.task_type.in_(CONTROL_TASK_TYPES))
        .order_by(ScraperTask.id.desc())
        .limit(limit)
        .all()
    )
    asr_rows = (
        db.query(AsrTask, LiveSession)
        .join(LiveSession, LiveSession.id == AsrTask.session_id)
        .order_by(AsrTask.id.desc())
        .limit(limit)
        .all()
    )
    chunk_counts = _asr_chunk_counts(db, [task.id for task, _session in asr_rows])
    items = [serialize_scraper_task(task) for task in scraper_tasks]
    items.extend(
        serialize_asr_task(task, session, chunk_counts.get(task.id, (0, 0)))
        for task, session in asr_rows
    )
    items.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
    return items[:limit]


def get_unified_task(db: Session, source: str, task_id: int) -> dict[str, Any] | None:
    if source == "scraper":
        task = db.get(ScraperTask, task_id)
        return serialize_scraper_task(task) if task and task.task_type in CONTROL_TASK_TYPES else None
    if source == "asr":
        row = (
            db.query(AsrTask, LiveSession)
            .join(LiveSession, LiveSession.id == AsrTask.session_id)
            .filter(AsrTask.id == task_id)
            .first()
        )
        if not row:
            return None
        counts = _asr_chunk_counts(db, [task_id]).get(task_id, (0, 0))
        return serialize_asr_task(row[0], row[1], counts)
    return None
