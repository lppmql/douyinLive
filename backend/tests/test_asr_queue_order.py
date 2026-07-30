from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.asr_tasks import AsrTask
from app.models.base import Base
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.services.asr.queue import (
    list_queued_task_ids_for_available_lanes,
    list_queued_task_ids_latest_first,
    queue_auto_transcriptions,
    queue_session_transcription,
)

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
        ],
    )
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(settings, "ASR_MAX_QUEUED", 10)

    room = LiveRoom(account_name="account", anchor_name="主播", platform="douyin", status=True)
    db.add(room)
    db.flush()

    sessions = []
    for start_time, duration in (
        (datetime(2026, 7, 14, 20, 0), 600),
        (datetime(2026, 7, 15, 20, 0), 1800),
        (datetime(2026, 7, 16, 20, 0), 5400),
    ):
        session = LiveSession(
            room_id=room.id,
            anchor_name="主播",
            live_start_time=start_time,
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
        live_start_time=datetime(2026, 7, 14, 18, 0),
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
            fetched_at=datetime(2026, 7, 14, 18, 0),
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


def test_live_task_can_wait_when_single_slot_is_used_by_offline_task():
    """单并发被离线任务占用时，直播任务仍要先入队，Worker 才能在分片边界礼让。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LiveRoom.__table__,
            LiveSession.__table__,
            StreamSource.__table__,
            AsrTask.__table__,
            AsrAudioChunk.__table__,
        ],
    )
    db = sessionmaker(bind=engine)()
    room = LiveRoom(account_name="account", anchor_name="主播", platform="douyin", status=True)
    db.add(room)
    db.flush()

    offline_session = LiveSession(
        room_id=room.id,
        anchor_name="离线主播",
        live_status="ended",
        detail_collection_status="complete",
    )
    live_session = LiveSession(
        room_id=room.id,
        anchor_name="实时主播",
        live_status="live",
        detail_collection_status="pending",
    )
    db.add_all([offline_session, live_session])
    db.flush()
    for session in (offline_session, live_session):
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

    live_task = db.query(AsrTask).filter(AsrTask.session_id == live_session.id).one()
    assert result["session_ids"] == [live_session.id]
    assert live_task.status == "queued"
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
        ],
    )
    db = sessionmaker(bind=engine)()
    room = LiveRoom(account_name="account", anchor_name="主播", platform="douyin", status=True)
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
