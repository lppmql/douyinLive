"""数据采集长期服务、最新优先与资源保护的回归测试。"""

import asyncio
from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.core.status import TaskStatus
from app.models.asr_tasks import AsrTask
from app.models.collector_module_states import CollectorModuleState
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.scraper_tasks import ScraperTask
from app.models.transcript_segments import TranscriptSegment
from app.services.resources.system_usage import _parse_size, _pressure, get_system_usage
from app.services.tasks.batch_runners import (
    _pending_ai_session_ids,
    _pending_knowledge_session_ids,
    pending_ai_session_count,
)
from app.services.tasks.module_service import CollectorModuleServiceManager, MODULE_KEYS


def _use_test_database(monkeypatch) -> None:
    """让模块服务和任务队列都使用隔离数据库，避免测试碰到真实业务数据。"""
    import app.services.tasks.control as control_module
    import app.services.tasks.module_service as module_service
    from conftest import TestSessionLocal

    monkeypatch.setattr(control_module, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(module_service, "SessionLocal", TestSessionLocal)


def test_knowledge_automatic_service_stays_enabled_when_there_is_no_pending_work(db, monkeypatch):
    _use_test_database(monkeypatch)
    db.add(
        CollectorModuleState(
            module_key="knowledge",
            enabled=False,
            interval_seconds=120,
        )
    )
    db.commit()

    manager = CollectorModuleServiceManager()
    monkeypatch.setattr(manager, "_pending_count", lambda _db, _key: 0)
    monkeypatch.setattr(
        "app.services.tasks.module_service.get_system_usage",
        lambda: {"pressure_level": "normal", "pressure_message": "资源正常"},
    )

    task, message = asyncio.run(manager.enable("knowledge"))

    db.expire_all()
    state = db.get(CollectorModuleState, "knowledge")
    assert task is None
    assert state.enabled is True
    assert state.next_run_at is not None
    assert "后台自动服务" in message


def test_knowledge_automatic_service_cannot_be_disabled(db, monkeypatch):
    _use_test_database(monkeypatch)
    db.add(
        CollectorModuleState(
            module_key="knowledge",
            enabled=True,
            interval_seconds=120,
            enabled_at=datetime.utcnow(),
        )
    )
    task = ScraperTask(
        id=2001,
        task_type="knowledge_sync",
        status=TaskStatus.PENDING,
        progress_stage="queued",
        progress_message="等待执行",
    )
    db.add(task)
    db.commit()
    manager = CollectorModuleServiceManager()
    with pytest.raises(ValueError, match="后台基础服务"):
        asyncio.run(manager.disable("knowledge"))

    db.expire_all()
    state = db.get(CollectorModuleState, "knowledge")
    assert state.enabled is True
    assert task.status == TaskStatus.PENDING


def test_restart_recovery_processes_all_pending_sessions_without_legacy_limit(db, monkeypatch):
    _use_test_database(monkeypatch)
    # 测试必须明确使用“0 代表不限制”，避免开发机旧环境变量把回归测试重新限制为 20 场。
    monkeypatch.setattr(settings, "CONTINUOUS_TASK_BATCH_SIZE", 0)
    task = ScraperTask(
        id=2002,
        task_type="knowledge_sync",
        status=TaskStatus.RUNNING,
        task_options_json={},
        progress_stage="knowledge_sync",
        progress_message="旧版全量任务",
    )
    db.add(task)
    db.commit()

    from app.services.tasks.control import CollectorTaskControlManager

    recovered_count = CollectorTaskControlManager().recover_interrupted_tasks()

    db.expire_all()
    recovered = db.get(ScraperTask, task.id)
    assert recovered_count == 1
    assert recovered.status == TaskStatus.PENDING
    assert recovered.task_options_json["continuous"] is True
    assert recovered.task_options_json["latest_first"] is True
    assert recovered.task_options_json["batch_size"] is None
    assert "全部待处理场次" in recovered.progress_message


def test_initial_state_table_contains_action_switches_and_automatic_modules(db, monkeypatch):
    _use_test_database(monkeypatch)

    CollectorModuleServiceManager().ensure_states()

    db.expire_all()
    states = db.query(CollectorModuleState).all()
    assert {state.module_key for state in states} == set(MODULE_KEYS)
    assert all(state.interval_seconds >= 5 for state in states)
    states_by_key = {state.module_key: state for state in states}
    assert states_by_key["data_refresh"].enabled is False
    assert states_by_key["knowledge"].enabled is True


def test_live_draft_never_enters_ai_or_knowledge_candidates(db):
    """直播初稿只供页面观察，自动 AI 和知识库必须等待离线终稿。"""
    room = LiveRoom(account_name="终稿隔离账号", anchor_name="测试主播", room_id_str="room-final-only")
    db.add(room)
    db.flush()
    realtime_session = LiveSession(
        room_id=room.id,
        anchor_name="直播中主播",
        live_status="live",
        detail_collection_status="complete",
        live_start_time=datetime.utcnow(),
    )
    offline_session = LiveSession(
        room_id=room.id,
        anchor_name="已下播主播",
        live_status="ended",
        detail_collection_status="complete",
        live_start_time=datetime.utcnow() - timedelta(hours=1),
    )
    db.add_all([realtime_session, offline_session])
    db.flush()
    db.add_all(
        [
            AsrTask(
                session_id=realtime_session.id,
                status="completed",
                task_type="realtime",
                idempotency_key=f"asr:realtime:session:{realtime_session.id}",
            ),
            AsrTask(
                session_id=offline_session.id,
                status="completed",
                task_type="offline",
                idempotency_key=f"asr:offline:session:{offline_session.id}",
            ),
            TranscriptSegment(
                session_id=realtime_session.id,
                text_content="直播临时初稿",
                segment_type="asr_realtime",
                asr_status="completed",
            ),
            TranscriptSegment(
                session_id=offline_session.id,
                text_content="下播后的最终稿",
                segment_type="asr_offline",
                asr_status="completed",
            ),
        ]
    )
    db.commit()

    assert _pending_ai_session_ids(db) == [offline_session.id]
    assert pending_ai_session_count(db) == 1
    assert _pending_knowledge_session_ids(db) == [offline_session.id]


def test_resource_snapshot_uses_real_system_values_and_pressure_thresholds():
    snapshot = get_system_usage(force=True)

    assert 0 <= snapshot["cpu_percent"] <= 100
    assert 0 <= snapshot["memory_percent"] <= 100
    assert snapshot["memory_total_bytes"] > 0
    assert snapshot["disk_free_bytes"] >= 0
    assert {item["key"] for item in snapshot["components"]} == {
        "backend",
        "chromium",
        "asr_worker",
        "ffmpeg",
        "funasr",
    }
    assert _parse_size("1.5GiB") == int(1.5 * 1024**3)
    assert _pressure(0, 100)[0] == "critical"
