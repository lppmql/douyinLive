"""ASR 转写任务排队，供接口、采集完成和下播处理共用。"""
from datetime import datetime

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asr_tasks import AsrTask
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.services.tasks.runtime import ensure_task_identity


def reset_failed_task_for_retry(task: AsrTask, failed_chunks: list[AsrAudioChunk], stream_id: int) -> None:
    """手动重试失败任务，保留完成分片，只重置失败部分。"""
    for chunk in failed_chunks:
        chunk.status = "pending"
        chunk.retry_count = 0
        chunk.error_message = None
        chunk.completed_at = None
        chunk.worker_id = None
    task.stream_id = stream_id
    task.status = "queued"
    task.retry_count = 0
    task.error_message = None
    task.started_at = None
    task.completed_at = None
    task.worker_id = None
    task.heartbeat_at = None
    task.postprocess_status = "pending"
    task.postprocess_started_at = None
    task.postprocess_completed_at = None
    task.postprocess_error = None
    task.postprocess_attempt_count = 0
    task.postprocess_result = None
    ensure_task_identity(task, "asr", f"asr:session:{task.session_id}")


def queue_session_transcription(db: Session, session: LiveSession) -> tuple[AsrTask, bool]:
    """幂等创建单场转写任务，并优先复用最近的有效流源。"""
    stream = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session.id, StreamSource.status == "active")
        .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .first()
    )
    if not stream and session.stream_url:
        stream = StreamSource(
            session_id=session.id,
            m3u8_url=session.stream_url[:2000],
            headers_json={"Referer": session.dashboard_url or ""},
            status="active",
            fetched_at=datetime.utcnow(),
        )
        db.add(stream)
        db.flush()
    if not stream:
        raise ValueError("该场次暂无可用直播流，请先重新采集流地址")

    existing = (
        db.query(AsrTask)
        .filter(AsrTask.session_id == session.id)
        .order_by(AsrTask.created_at.desc())
        .first()
    )
    if existing:
        if existing.status == "failed":
            failed_chunks = db.query(AsrAudioChunk).filter(
                AsrAudioChunk.task_id == existing.id,
                AsrAudioChunk.status == "failed",
            ).all()
            reset_failed_task_for_retry(existing, failed_chunks, stream.id)
            db.flush()
            return existing, True
        return existing, False

    task = AsrTask(session_id=session.id, stream_id=stream.id, status="queued", task_type="offline")
    ensure_task_identity(task, "asr", f"asr:session:{session.id}")
    db.add(task)
    db.flush()
    return task, True


def queue_auto_transcriptions(
    db: Session,
    limit: int | None = None,
    session_ids: list[int] | None = None,
) -> dict:
    """在全局容量内为可安全离线处理的真实场次自动排队。"""
    capacity = max(1, settings.ASR_MAX_QUEUED)
    active_count = db.query(AsrTask).filter(AsrTask.status.in_(["queued", "processing"])).count()
    available = max(0, capacity - active_count)
    if limit is not None:
        available = min(available, max(0, limit))
    if available == 0:
        return {"created_count": 0, "active_count": active_count, "capacity": capacity, "session_ids": []}

    has_stream = or_(
        LiveSession.stream_url.isnot(None),
        exists().where(
            StreamSource.session_id == LiveSession.id,
            StreamSource.status == "active",
        ),
    )
    has_any_task = exists().where(AsrTask.session_id == LiveSession.id)
    query = db.query(LiveSession).filter(
            LiveSession.detail_collection_status == "complete",
            LiveSession.live_status != "live",
            has_stream,
            ~has_any_task,
        )
    if session_ids is not None:
        query = query.filter(LiveSession.id.in_(session_ids))
    sessions = (
        query
        .order_by(LiveSession.live_duration_seconds.asc(), LiveSession.live_start_time.desc())
        .limit(available)
        .all()
    )

    session_ids = []
    for session in sessions:
        try:
            _task, created = queue_session_transcription(db, session)
        except ValueError:
            continue
        if created:
            session_ids.append(session.id)
    db.commit()
    return {
        "created_count": len(session_ids),
        "active_count": active_count + len(session_ids),
        "capacity": capacity,
        "session_ids": session_ids,
    }
