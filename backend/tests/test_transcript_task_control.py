from datetime import datetime
from unittest.mock import patch

from app.core.status import TaskStatus
from app.models.asr_tasks import AsrTask
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.services.asr.queue import queue_session_transcription
from app.services.asr.task_control import (
    release_manual_priority,
    request_stop_asr_task,
    retry_asr_task,
)


def _seed_manual_task(db) -> AsrTask:
    session = LiveSession(
        room_id=9901,
        anchor_name="任务控制测试主播",
        live_status="ended",
        detail_collection_status="complete",
        live_start_time=datetime(2026, 8, 18, 9, 0),
        live_end_time=datetime(2026, 8, 18, 10, 0),
    )
    db.add(session)
    db.flush()
    db.add(
        StreamSource(
            session_id=session.id,
            m3u8_url="https://example.invalid/task-control.m3u8",
            status="active",
            fetched_at=datetime(2026, 8, 18, 10, 1),
        )
    )
    db.flush()
    task, _created = queue_session_transcription(
        db, session, queue_source="manual"
    )
    db.commit()
    return task


def test_manual_task_can_release_stop_and_resume_from_checkpoint(db):
    task = _seed_manual_task(db)

    with patch("app.services.asr.task_control.publish_task_event"):
        released = release_manual_priority(db, task.id)
        assert released.queue_source == "auto"
        assert released.priority == 50

        stopped = request_stop_asr_task(db, task.id)
        assert stopped.status == TaskStatus.CANCELLED
        assert stopped.cancel_requested_at is not None

        retried = retry_asr_task(db, task.id)
        assert retried.id == task.id
        assert retried.status == TaskStatus.QUEUED
        assert retried.queue_source == "auto"
        assert retried.cancel_requested_at is None


def test_task_status_api_counts_cancelled_as_needing_attention(
    db, client, auth_headers
):
    task = _seed_manual_task(db)
    with patch("app.services.asr.task_control.publish_task_event"):
        request_stop_asr_task(db, task.id)

    response = client.get("/api/v1/transcripts/tasks/status", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["cancelled"] == 1
    assert payload["needs_attention"] == payload["failed"] + 1

    task_response = client.get(
        "/api/v1/transcripts/tasks", headers=auth_headers
    )
    assert task_response.status_code == 200
    stopped_task = next(item for item in task_response.json() if item["id"] == task.id)
    assert stopped_task["status"] == TaskStatus.CANCELLED
    assert stopped_task["cancel_requested"] is False
