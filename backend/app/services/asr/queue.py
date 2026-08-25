"""ASR 转写任务排队，供接口、采集完成和下播处理共用。"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.asr_tasks import AsrTask
from app.models.asr_dispatch_policies import AsrDispatchPolicy
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.models.base import utc_now_naive
from app.services.tasks.runtime import ensure_task_identity
from app.core.status import TaskStatus


AUTO_SCOPE_TIMEZONE = "Asia/Shanghai"
ASR_ORDER_MODES = {"smart", "latest", "fifo"}


def automatic_session_scope_clause(now: datetime | None = None):
    """自动转写范围：全部直播中场次，以及上海自然日内结束的场次。"""
    local_now = now or datetime.now(ZoneInfo(AUTO_SCOPE_TIMEZONE))
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=ZoneInfo(AUTO_SCOPE_TIMEZONE))
    else:
        local_now = local_now.astimezone(ZoneInfo(AUTO_SCOPE_TIMEZONE))
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).replace(
        tzinfo=None
    )
    tomorrow_start = today_start + timedelta(days=1)
    ended_at = func.coalesce(LiveSession.live_end_time, LiveSession.live_start_time)
    return or_(
        LiveSession.live_status == "live",
        and_(
            LiveSession.live_status != "live",
            ended_at >= today_start,
            ended_at < tomorrow_start,
        ),
    )


def get_dispatch_policy(db: Session) -> AsrDispatchPolicy:
    """读取单例策略；旧测试库或迁移后空表会自动补默认行。"""
    policy = db.get(AsrDispatchPolicy, 1)
    if policy is None:
        policy = AsrDispatchPolicy(id=1, order_mode="smart")
        db.add(policy)
        db.flush()
    if policy.order_mode not in ASR_ORDER_MODES:
        policy.order_mode = "smart"
    return policy


def get_active_manual_task(
    db: Session, *, exclude_task_id: int | None = None
) -> AsrTask | None:
    """返回当前人工独占任务；人工排队和处理中都算占用。"""
    query = db.query(AsrTask).filter(
        AsrTask.queue_source == "manual",
        AsrTask.status.in_([TaskStatus.QUEUED, TaskStatus.PROCESSING]),
        AsrTask.cancel_requested_at.is_(None),
    )
    if exclude_task_id is not None:
        query = query.filter(AsrTask.id != exclude_task_id)
    return query.order_by(
        AsrTask.priority.asc(), AsrTask.created_at.asc(), AsrTask.id.asc()
    ).first()


def activate_manual_exclusive_task(db: Session, task: AsrTask) -> None:
    """把指定任务设为唯一人工任务；其他任务保留断点并在安全边界暂停。"""
    db.query(AsrTask).filter(
        AsrTask.id != task.id,
        AsrTask.queue_source == "manual",
        AsrTask.status.in_([TaskStatus.QUEUED, TaskStatus.PROCESSING]),
    ).update(
        {AsrTask.queue_source: "auto", AsrTask.priority: 50},
        synchronize_session=False,
    )
    task.queue_source = "manual"
    task.priority = 0
    task.cancel_requested_at = None


def stop_auto_tasks_outside_scope(db: Session) -> int:
    """停止超出今日范围的自动任务；已完成分片保留，可再次手动转写。"""
    rows = (
        db.query(AsrTask)
        .join(LiveSession, LiveSession.id == AsrTask.session_id)
        .filter(
            AsrTask.queue_source == "auto",
            AsrTask.status.in_([TaskStatus.QUEUED, TaskStatus.PROCESSING]),
            ~automatic_session_scope_clause(),
        )
        .all()
    )
    now = utc_now_naive()
    for task in rows:
        message = "超出今日自动转写范围，已保留断点；如需继续请手动选择该场次"
        task.error_message = message
        if task.status == TaskStatus.PROCESSING:
            task.cancel_requested_at = now
        else:
            task.status = TaskStatus.CANCELLED
            task.completed_at = now
    return len(rows)


def recover_interrupted_chunk(chunk: AsrAudioChunk) -> None:
    """恢复被 Worker 重启打断的分片，不消耗正常业务重试次数。"""
    chunk.status = TaskStatus.PENDING
    chunk.retry_count = max(0, int(chunk.retry_count or 0) - 1)
    chunk.error_message = "Worker 中断，已保留完成内容并等待断点续传"
    chunk.completed_at = None
    chunk.worker_id = None
    chunk.heartbeat_at = datetime.utcnow()


def requeue_task_for_dispatch(task: AsrTask, message: str) -> None:
    """任务在安全边界礼让更高优先级任务，并退还本次任务级重试次数。"""
    task.status = TaskStatus.QUEUED
    task.retry_count = max(0, int(task.retry_count or 0) - 1)
    task.error_message = message[:500]
    task.started_at = None
    task.completed_at = None
    task.worker_id = None
    task.heartbeat_at = datetime.utcnow()


def requeue_offline_task_for_live_priority(task: AsrTask) -> None:
    """兼容旧调用：离线任务礼让实时直播。"""
    requeue_task_for_dispatch(task, "检测到正在直播的任务，已保存断点并主动礼让")


def reset_failed_task_for_retry(
    task: AsrTask, failed_chunks: list[AsrAudioChunk], stream_id: int
) -> None:
    """手动重试失败任务，保留完成分片，只重置失败部分。"""
    for chunk in failed_chunks:
        chunk.status = TaskStatus.PENDING
        chunk.retry_count = 0
        chunk.error_message = None
        chunk.completed_at = None
        chunk.worker_id = None
    task.stream_id = stream_id
    task.status = TaskStatus.QUEUED
    task.retry_count = 0
    task.error_message = None
    task.started_at = None
    task.completed_at = None
    task.worker_id = None
    task.heartbeat_at = None
    task.cancel_requested_at = None
    task.postprocess_status = "skipped"
    task.postprocess_started_at = None
    task.postprocess_completed_at = None
    task.postprocess_error = None
    task.postprocess_attempt_count = 0
    task.postprocess_result = None
    ensure_task_identity(task, "asr", f"asr:session:{task.session_id}")


def queue_session_transcription(
    db: Session,
    session: LiveSession,
    *,
    queue_source: str = "auto",
) -> tuple[AsrTask, bool]:
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

    expected_task_type = "realtime" if session.live_status == "live" else "offline"
    existing = (
        db.query(AsrTask)
        .filter(
            AsrTask.session_id == session.id,
            AsrTask.task_type == expected_task_type,
        )
        .order_by(AsrTask.created_at.desc())
        .first()
    )
    if existing:
        if existing.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            failed_chunks = (
                db.query(AsrAudioChunk)
                .filter(
                    AsrAudioChunk.task_id == existing.id,
                    AsrAudioChunk.status == "failed",
                )
                .all()
            )
            reset_failed_task_for_retry(existing, failed_chunks, stream.id)
            existing.queue_source = queue_source
            existing.priority = 0 if queue_source == "manual" else 50
            if queue_source == "manual":
                activate_manual_exclusive_task(db, existing)
            db.flush()
            return existing, True
        if queue_source == "manual" and existing.status != TaskStatus.COMPLETED:
            activate_manual_exclusive_task(db, existing)
            db.flush()
        return existing, False

    task = AsrTask(
        session_id=session.id,
        stream_id=stream.id,
        status=TaskStatus.QUEUED,
        task_type=expected_task_type,
        queue_source=queue_source,
        priority=0 if queue_source == "manual" else 50,
        postprocess_status="skipped",
    )
    ensure_task_identity(task, "asr", f"asr:{expected_task_type}:session:{session.id}")
    db.add(task)
    db.flush()
    if queue_source == "manual":
        activate_manual_exclusive_task(db, task)
        db.flush()
    return task, True


def list_queued_task_ids_latest_first(db: Session, limit: int) -> list[int]:
    """人工任务绝对优先；自动任务始终直播优先，再使用页面选择的排序。"""
    active_manual = get_active_manual_task(db)
    if active_manual:
        return [active_manual.id] if active_manual.status == TaskStatus.QUEUED else []

    return list_all_queued_task_ids_for_display(db, limit)


def list_all_queued_task_ids_for_display(db: Session, limit: int) -> list[int]:
    """返回完整排队顺序；页面可展示被人工独占暂时阻塞的自动任务。"""

    order_mode = get_dispatch_policy(db).order_mode
    if order_mode == "fifo":
        secondary_order = (AsrTask.created_at.asc(), AsrTask.id.asc())
    elif order_mode == "latest":
        secondary_order = (
            LiveSession.live_start_time.desc(),
            LiveSession.id.desc(),
            AsrTask.priority.asc(),
        )
    else:
        secondary_order = (
            AsrTask.priority.asc(),
            LiveSession.live_start_time.desc(),
            LiveSession.id.desc(),
            AsrTask.created_at.asc(),
        )
    return [
        row[0]
        for row in (
            db.query(AsrTask)
            .join(LiveSession, LiveSession.id == AsrTask.session_id)
            .filter(
                AsrTask.status == TaskStatus.QUEUED,
                AsrTask.cancel_requested_at.is_(None),
            )
            .with_entities(AsrTask.id)
            .order_by(
                case((AsrTask.queue_source == "manual", 0), else_=1),
                case((LiveSession.live_status == "live", 0), else_=1),
                *secondary_order,
            )
            .limit(limit)
            .all()
        )
    ]


def list_queued_task_ids_for_available_lanes(
    db: Session,
    limit: int,
    *,
    occupied_lanes: set[str] | None = None,
) -> list[int]:
    """每种逻辑通道最多领取一个任务，并保留各通道原有优先顺序。"""
    occupied = set(occupied_lanes or set())
    ordered_ids = list_queued_task_ids_latest_first(
        db,
        max(settings.ASR_MAX_QUEUED, limit),
    )
    if not ordered_ids:
        return []
    task_types = dict(
        db.query(AsrTask.id, AsrTask.task_type)
        .filter(AsrTask.id.in_(ordered_ids))
        .all()
    )
    selected: list[int] = []
    selected_lanes = set(occupied)
    for task_id in ordered_ids:
        lane = str(task_types.get(task_id) or "")
        if lane not in {"realtime", "offline"} or lane in selected_lanes:
            continue
        selected.append(task_id)
        selected_lanes.add(lane)
        if len(selected) >= max(0, limit):
            break
    return selected


def queue_auto_transcriptions(
    db: Session,
    limit: int | None = None,
    session_ids: list[int] | None = None,
    queue_capacity: int | None = None,
) -> dict:
    """自动排队全部直播场次和上海自然日内已经下播的场次。"""
    stopped_count = stop_auto_tasks_outside_scope(db)
    if stopped_count:
        db.flush()
    capacity = (
        max(0, int(queue_capacity))
        if queue_capacity is not None
        else max(1, settings.ASR_MAX_QUEUED)
    )
    active_count = (
        db.query(AsrTask)
        .filter(AsrTask.status.in_([TaskStatus.QUEUED, "processing"]))
        .count()
    )
    automatic_budget = max(0, capacity - active_count)
    if limit is not None:
        automatic_budget = min(automatic_budget, max(0, limit))

    has_stream = or_(
        LiveSession.stream_url.isnot(None),
        exists().where(
            StreamSource.session_id == LiveSession.id,
            StreamSource.status == "active",
        ),
    )
    has_realtime_task = exists().where(
        AsrTask.session_id == LiveSession.id,
        AsrTask.task_type == "realtime",
    )
    has_offline_task = exists().where(
        AsrTask.session_id == LiveSession.id,
        AsrTask.task_type == "offline",
    )

    # 模块关闭产生的 cancelled 任务不是人工放弃；重新开启后优先从已完成分片继续。
    resumable_query = (
        db.query(LiveSession)
        .join(AsrTask, AsrTask.session_id == LiveSession.id)
        .filter(
            AsrTask.status == TaskStatus.CANCELLED,
            AsrTask.error_message.like("ASR 开关已关闭%"),
            has_stream,
            automatic_session_scope_clause(),
        )
        .order_by(
            case((LiveSession.live_status == "live", 0), else_=1),
            LiveSession.live_start_time.desc(),
            LiveSession.id.desc(),
        )
    )
    if session_ids is not None:
        resumable_query = resumable_query.filter(LiveSession.id.in_(session_ids))

    # 所有正在直播的场次都必须进入等待队列。容量和页面 limit 只约束今日已下播场次，
    # 否则单并发或多主播同时开播时，未排队的直播永远无法触发 Worker 礼让。
    created_session_ids: list[int] = []
    live_resumable = resumable_query.filter(LiveSession.live_status == "live").all()
    for session in live_resumable:
        try:
            _task, resumed = queue_session_transcription(db, session)
        except ValueError:
            continue
        if resumed:
            created_session_ids.append(session.id)

    live_query = db.query(LiveSession).filter(
        LiveSession.live_status == "live",
        has_stream,
        ~has_realtime_task,
    )
    if session_ids is not None:
        live_query = live_query.filter(LiveSession.id.in_(session_ids))
    for session in live_query.order_by(
        LiveSession.live_start_time.desc(), LiveSession.id.desc()
    ).all():
        try:
            _task, created = queue_session_transcription(db, session)
        except ValueError:
            continue
        if created:
            created_session_ids.append(session.id)

    ended_budget = max(0, automatic_budget - len(created_session_ids))
    ended_resumable = resumable_query.filter(LiveSession.live_status != "live")
    for session in ended_resumable.limit(ended_budget).all():
        try:
            _task, resumed = queue_session_transcription(db, session)
        except ValueError:
            continue
        if resumed:
            created_session_ids.append(session.id)
    ended_budget = max(0, automatic_budget - len(created_session_ids))

    ended_query = db.query(LiveSession).filter(
        LiveSession.live_status != "live",
        automatic_session_scope_clause(),
        LiveSession.detail_collection_status == "complete",
        has_stream,
        ~has_offline_task,
    )
    if session_ids is not None:
        ended_query = ended_query.filter(LiveSession.id.in_(session_ids))
    ended_sessions = []
    if ended_budget:
        ended_sessions = (
            ended_query.order_by(
                LiveSession.live_start_time.desc(), LiveSession.id.desc()
            )
            .limit(ended_budget)
            .all()
        )

    for session in ended_sessions:
        try:
            _task, created = queue_session_transcription(db, session)
        except ValueError:
            continue
        if created:
            created_session_ids.append(session.id)
    db.commit()
    return {
        "created_count": len(created_session_ids),
        "active_count": active_count + len(created_session_ids),
        "capacity": capacity,
        "session_ids": created_session_ids,
        "stopped_outside_scope": stopped_count,
    }
