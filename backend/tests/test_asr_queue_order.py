from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.asr_tasks import AsrTask
from app.models.base import Base
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.services.asr.queue import (
    list_queued_task_ids_latest_first,
    queue_auto_transcriptions,
    queue_session_transcription,
)


@compiles(BigInteger, "sqlite")
def compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    """SQLite 只有 INTEGER 主键支持自增，测试时兼容 MySQL BIGINT 主键。"""
    return "INTEGER"


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

    result = queue_auto_transcriptions(db, limit=2)

    assert result["session_ids"] == [sessions[2].id, sessions[1].id]

    oldest_task, created = queue_session_transcription(db, sessions[0])
    assert created is True
    oldest_task.priority = 10
    db.commit()

    queued_ids = list_queued_task_ids_latest_first(db, 3)
    latest_task = db.query(AsrTask).filter(AsrTask.session_id == sessions[2].id).one()
    middle_task = db.query(AsrTask).filter(AsrTask.session_id == sessions[1].id).one()

    assert queued_ids == [oldest_task.id, latest_task.id, middle_task.id]
    db.close()
