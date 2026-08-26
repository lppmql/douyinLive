from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.status import TaskStatus
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.asr_tasks import AsrTask
from app.models.asr_dispatch_policies import AsrDispatchPolicy
from app.models.base import Base
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.services.asr.queue import (
    list_queued_task_ids_for_available_lanes,
    list_queued_task_ids_latest_first,
    queue_auto_transcriptions,
    queue_session_transcription,
    requeue_task_for_dispatch,
)
from workers.asr_worker import AsrWorker


def test_auto_queue_and_worker_default_to_latest_real_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LiveRoom.__table__,
            LiveSession.__table__,
            StreamSource.__table__,
            AsrTask.__table__,
            AsrAudioChunk.__table__,
            AsrDispatchPolicy.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(settings, "ASR_MAX_QUEUED", 10)

    room = LiveRoom(
        account_name="account", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()

    today = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        tzinfo=None, hour=0, minute=0, second=0, microsecond=0
    )
    sessions = []
    for start_time, duration in (
        (today.replace(hour=9), 600),
        (today.replace(hour=12), 1800),
        (today.replace(hour=15), 5400),
    ):
        session = LiveSession(
            room_id=room.id,
            anchor_name="主播",
            live_start_time=start_time,
            live_end_time=start_time + timedelta(seconds=duration),
            live_duration_seconds=duration,
            live_status="ended",
            detail_collection_status="complete",
        )
        db.add(session)
        db.flush()
        db.add(
            StreamSource(
                session_id=session.id,
                m3u8_url=f"https://example.invalid/{session.id}.m3u8",
                status="active",
                fetched_at=start_time,
            )
        )
        sessions.append(session)
    db.commit()

    live_session = LiveSession(
        room_id=room.id,
        anchor_name="正在开播主播",
        live_start_time=today - timedelta(days=3),
        live_status="live",
        detail_collection_status="pending",
    )
    db.add(live_session)
    db.flush()
    db.add(
        StreamSource(
            session_id=live_session.id,
            m3u8_url=f"https://example.invalid/{live_session.id}.m3u8",
            status="active",
            fetched_at=today,
        )
    )
    db.commit()

    result = queue_auto_transcriptions(db, limit=2)

    assert result["session_ids"] == [live_session.id, sessions[2].id]

    oldest_task, created = queue_session_transcription(db, sessions[0])
    assert created is True
    oldest_task.priority = 10
    db.commit()

    queued_ids = list_queued_task_ids_latest_first(db, 3)
    live_task = db.query(AsrTask).filter(AsrTask.session_id == live_session.id).one()
    latest_task = db.query(AsrTask).filter(AsrTask.session_id == sessions[2].id).one()

    assert queued_ids == [live_task.id, oldest_task.id, latest_task.id]
    lane_ids = list_queued_task_ids_for_available_lanes(db, 2)
    assert lane_ids == [live_task.id, oldest_task.id]
    assert list_queued_task_ids_for_available_lanes(
        db,
        2,
        occupied_lanes={"realtime"},
    ) == [oldest_task.id]
    db.close()


def test_all_live_tasks_can_wait_when_single_slot_is_used_by_offline_task():
    """单并发被离线占用时，所有直播都要入队，Worker 才能依次实时转写。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LiveRoom.__table__,
            LiveSession.__table__,
            StreamSource.__table__,
            AsrTask.__table__,
            AsrAudioChunk.__table__,
            AsrDispatchPolicy.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    room = LiveRoom(
        account_name="account", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()

    offline_session = LiveSession(
        room_id=room.id,
        anchor_name="离线主播",
        live_status="ended",
        detail_collection_status="complete",
        live_start_time=datetime.now().replace(
            hour=9, minute=0, second=0, microsecond=0
        ),
        live_end_time=datetime.now().replace(
            hour=10, minute=0, second=0, microsecond=0
        ),
    )
    live_sessions = [
        LiveSession(
            room_id=room.id,
            anchor_name=f"实时主播{index}",
            live_status="live",
            detail_collection_status="pending",
        )
        for index in range(1, 4)
    ]
    db.add_all([offline_session, *live_sessions])
    db.flush()
    for session in (offline_session, *live_sessions):
        db.add(
            StreamSource(
                session_id=session.id,
                m3u8_url=f"https://example.invalid/{session.id}.m3u8",
                status="active",
                fetched_at=datetime(2026, 7, 27, 20, 0),
            )
        )
    db.flush()
    offline_task, _created = queue_session_transcription(db, offline_session)
    offline_task.status = "processing"
    db.commit()

    result = queue_auto_transcriptions(db, limit=1, queue_capacity=1)

    assert set(result["session_ids"]) == {session.id for session in live_sessions}
    live_tasks = (
        db.query(AsrTask)
        .filter(AsrTask.session_id.in_([session.id for session in live_sessions]))
        .all()
    )
    assert len(live_tasks) == 3
    assert all(task.status == TaskStatus.QUEUED for task in live_tasks)
    assert offline_task.status == "processing"
    db.close()


def test_finished_live_creates_separate_offline_final_task():
    """直播初稿完成后，下播必须再创建独立最终稿，不能把初稿当最终结果。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LiveRoom.__table__,
            LiveSession.__table__,
            StreamSource.__table__,
            AsrTask.__table__,
            AsrAudioChunk.__table__,
            AsrDispatchPolicy.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    room = LiveRoom(
        account_name="account", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播",
        live_start_time=datetime(2026, 7, 27, 10, 0),
        live_status="live",
        detail_collection_status="complete",
    )
    db.add(session)
    db.flush()
    db.add(
        StreamSource(
            session_id=session.id,
            m3u8_url="https://example.invalid/handoff.m3u8",
            status="active",
            fetched_at=datetime(2026, 7, 27, 10, 0),
        )
    )
    db.flush()
    live_task, created = queue_session_transcription(db, session)
    live_task.status = "completed"
    db.commit()
    assert created is True
    assert live_task.task_type == "realtime"

    session.live_status = "ended"
    session.live_end_time = datetime(2026, 7, 27, 11, 0)
    session.live_duration_seconds = 3600
    db.commit()
    offline_task, created = queue_session_transcription(db, session)
    db.commit()

    assert created is True
    assert offline_task.id != live_task.id
    assert offline_task.task_type == "offline"
    assert offline_task.idempotency_key == f"asr:offline:session:{session.id}"
    db.close()


def test_auto_scope_queues_yesterday_and_today_but_keeps_all_live_sessions():
    """前天下播不自动转写；昨天、今天下播和全部直播中场次必须入队。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LiveRoom.__table__,
            LiveSession.__table__,
            StreamSource.__table__,
            AsrTask.__table__,
            AsrAudioChunk.__table__,
            AsrDispatchPolicy.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    room = LiveRoom(
        account_name="account", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    today = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        tzinfo=None, hour=0, minute=0, second=0, microsecond=0
    )
    day_before_yesterday = LiveSession(
        room_id=room.id,
        anchor_name="前天下播",
        live_start_time=today - timedelta(days=2),
        live_end_time=today - timedelta(days=2, hours=-1),
        live_status="ended",
        detail_collection_status="complete",
    )
    yesterday_ended = LiveSession(
        room_id=room.id,
        anchor_name="昨天下播",
        live_start_time=today - timedelta(days=1) + timedelta(hours=9),
        live_end_time=today - timedelta(days=1) + timedelta(hours=10),
        live_status="ended",
        detail_collection_status="complete",
    )
    today_ended = LiveSession(
        room_id=room.id,
        anchor_name="今日下播",
        live_start_time=today.replace(hour=9),
        live_end_time=today.replace(hour=10),
        live_status="ended",
        detail_collection_status="complete",
    )
    live = LiveSession(
        room_id=room.id,
        anchor_name="仍在直播",
        live_start_time=today - timedelta(days=2),
        live_status="live",
        detail_collection_status="pending",
    )
    db.add_all([day_before_yesterday, yesterday_ended, today_ended, live])
    db.flush()
    for session in (day_before_yesterday, yesterday_ended, today_ended, live):
        db.add(
            StreamSource(
                session_id=session.id,
                m3u8_url=f"https://example.invalid/{session.id}.m3u8",
                status="active",
                fetched_at=today,
            )
        )
    db.commit()

    result = queue_auto_transcriptions(db, limit=10, queue_capacity=10)

    assert set(result["session_ids"]) == {
        yesterday_ended.id,
        today_ended.id,
        live.id,
    }
    assert (
        db.query(AsrTask)
        .filter(AsrTask.session_id == day_before_yesterday.id)
        .count()
        == 0
    )
    db.close()


def test_manual_task_is_exclusive_and_auto_order_can_switch_to_fifo():
    """人工任务绝对优先；人工结束前不领取自动任务，自动排序可切换 FIFO。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LiveRoom.__table__,
            LiveSession.__table__,
            StreamSource.__table__,
            AsrTask.__table__,
            AsrAudioChunk.__table__,
            AsrDispatchPolicy.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    room = LiveRoom(
        account_name="account", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    today = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        tzinfo=None, hour=0, minute=0, second=0, microsecond=0
    )
    older = LiveSession(
        room_id=room.id,
        anchor_name="先排队",
        live_start_time=today.replace(hour=8),
        live_end_time=today.replace(hour=9),
        live_status="ended",
        detail_collection_status="complete",
    )
    latest = LiveSession(
        room_id=room.id,
        anchor_name="后开播",
        live_start_time=today.replace(hour=12),
        live_end_time=today.replace(hour=13),
        live_status="ended",
        detail_collection_status="complete",
    )
    db.add_all([older, latest])
    db.flush()
    for session in (older, latest):
        db.add(
            StreamSource(
                session_id=session.id,
                m3u8_url=f"https://example.invalid/{session.id}.m3u8",
                status="active",
                fetched_at=today,
            )
        )
    db.flush()
    older_task, _ = queue_session_transcription(db, older)
    latest_task, _ = queue_session_transcription(db, latest)
    db.commit()

    assert list_queued_task_ids_latest_first(db, 2) == [latest_task.id, older_task.id]
    policy = db.get(AsrDispatchPolicy, 1)
    policy.order_mode = "fifo"
    db.commit()
    assert list_queued_task_ids_latest_first(db, 2) == [older_task.id, latest_task.id]

    manual_task, created = queue_session_transcription(
        db, latest, queue_source="manual"
    )
    db.commit()
    assert created is False
    assert manual_task.queue_source == "manual"
    assert manual_task.priority == 0
    assert list_queued_task_ids_latest_first(db, 2) == [manual_task.id]
    manual_task.status = TaskStatus.PROCESSING
    db.commit()
    assert list_queued_task_ids_latest_first(db, 2) == []
    assert AsrWorker._should_yield_to_manual(db, older_task) is True
    assert AsrWorker._should_yield_to_manual(db, manual_task) is False

    older_task.status = TaskStatus.PROCESSING
    older_task.retry_count = 1
    requeue_task_for_dispatch(older_task, "人工任务到来，保存断点")
    db.commit()
    assert older_task.status == TaskStatus.QUEUED
    assert older_task.retry_count == 0
    assert list_queued_task_ids_latest_first(db, 2) == []

    manual_task.status = TaskStatus.COMPLETED
    db.commit()
    assert list_queued_task_ids_latest_first(db, 2) == [older_task.id]
    db.close()
