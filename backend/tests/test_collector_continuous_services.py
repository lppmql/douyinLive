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
    run_ai_review_batch,
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
    assert states_by_key["ai_review"].enabled is True
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


def test_ai_review_waits_until_local_transcript_correction_is_stable(db, monkeypatch):
    """本地纠错还在排队或未用完重试时，不能拿旧终稿生成复盘。"""
    monkeypatch.setattr(settings, "ASR_LLM_CORRECTION_MAX_ATTEMPTS", 3)
    room = LiveRoom(
        account_name="终稿纠错门禁账号",
        anchor_name="测试主播",
        room_id_str="room-review-correction-gate",
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="已下播主播",
        live_status="ended",
        live_start_time=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(session)
    db.flush()
    task = AsrTask(
        session_id=session.id,
        status="completed",
        task_type="offline",
        postprocess_status="pending",
        postprocess_attempt_count=0,
        idempotency_key=f"asr:offline:session:{session.id}",
    )
    db.add_all(
        [
            task,
            TranscriptSegment(
                session_id=session.id,
                text_content="这是已经完成识别但还在等待本地模型纠错的真实终稿。",
                segment_type="asr_offline",
                asr_status="completed",
            ),
        ]
    )
    db.commit()

    assert _pending_ai_session_ids(db) == []

    task.postprocess_status = "failed"
    task.postprocess_attempt_count = 2
    db.commit()
    assert _pending_ai_session_ids(db) == []

    task.postprocess_attempt_count = 3
    db.commit()
    assert _pending_ai_session_ids(db) == [session.id]


def test_ai_review_automatic_batch_is_single_session_and_waits_for_asr(db, monkeypatch):
    """自动复盘固定单场串行，ASR 任务存在时不进入控制队列。"""
    _use_test_database(monkeypatch)
    manager = CollectorModuleServiceManager()
    state = CollectorModuleState(
        module_key="ai_review",
        enabled=True,
        interval_seconds=120,
        next_run_at=datetime.utcnow() - timedelta(seconds=1),
    )
    db.add(state)
    room = LiveRoom(
        account_name="AI 资源门禁账号",
        anchor_name="测试主播",
        room_id_str="room-ai-resource-gate",
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="测试主播",
        live_status="ended",
    )
    db.add(session)
    db.flush()
    db.commit()
    monkeypatch.setattr(manager, "_pending_count", lambda _db, _key: 1)

    asr_task = AsrTask(
        session_id=session.id,
        status=TaskStatus.QUEUED,
        task_type="offline",
        postprocess_status="pending",
        idempotency_key="asr:offline:session:automatic-review-gate",
    )
    db.add(asr_task)
    db.commit()
    manager._schedule_due_modules_sync(
        {"pressure_level": "normal", "pressure_message": "资源正常"}
    )
    assert db.query(ScraperTask).filter(ScraperTask.task_type == "ai_review").count() == 0

    asr_task.status = TaskStatus.COMPLETED
    asr_task.postprocess_status = TaskStatus.COMPLETED
    state.next_run_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    manager._schedule_due_modules_sync(
        {"pressure_level": "normal", "pressure_message": "资源正常"}
    )

    queued = db.query(ScraperTask).filter(ScraperTask.task_type == "ai_review").one()
    assert queued.task_options_json["batch_size"] == 1


def test_ai_review_batch_generates_score_findings_and_unified_review(db, monkeypatch):
    """后台任务必须产出页面使用的完整统一复盘，不能只做旧评分。"""
    room = LiveRoom(
        account_name="AI 完整复盘账号",
        anchor_name="测试主播",
        room_id_str="room-complete-ai-review",
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="测试主播",
        live_status="ended",
        live_start_time=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(session)
    db.flush()
    control_task = ScraperTask(
        task_type="ai_review",
        status=TaskStatus.RUNNING,
        progress_stage="ai_review",
    )
    db.add_all(
        [
            control_task,
            AsrTask(
                session_id=session.id,
                status="completed",
                task_type="offline",
                postprocess_status="completed",
                idempotency_key=f"asr:offline:session:complete-review:{session.id}",
            ),
            TranscriptSegment(
                session_id=session.id,
                text_content="这是已经完成转写和纠错的真实话术终稿，用于验证后台自动完整复盘。",
                segment_type="asr_offline",
                asr_status="completed",
            ),
        ]
    )
    db.commit()
    calls: list[str] = []
    monkeypatch.setattr(
        "app.services.tasks.batch_runners.score_session_transcript",
        lambda _session_id, _db: calls.append("score") or {"total_score": 80},
    )
    monkeypatch.setattr(
        "app.services.tasks.batch_runners.generate_findings",
        lambda _db, _session_id: calls.append("findings") or [],
    )
    monkeypatch.setattr(
        "app.services.tasks.batch_runners.generate_unified_review",
        lambda _db, _session_id: calls.append("unified")
        or {"status": "completed", "analyzed_user_count": 2},
    )

    result = run_ai_review_batch(
        db,
        control_task.id,
        lambda *_args: None,
        lambda: False,
        batch_size=1,
    )

    assert calls == ["score", "findings", "unified"]
    assert result["completed_count"] == 1
    assert result["failed_count"] == 0


def test_ai_review_batch_degrades_score_failure_without_losing_unified_review(
    db, monkeypatch
):
    """话术评分异常只记警告，已成功的完整复盘不能被误标失败。"""
    room = LiveRoom(
        account_name="AI 评分降级账号",
        anchor_name="测试主播",
        room_id_str="room-ai-score-degradation",
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="测试主播",
        live_status="ended",
        live_start_time=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(session)
    db.flush()
    control_task = ScraperTask(
        task_type="ai_review",
        status=TaskStatus.RUNNING,
        progress_stage="ai_review",
    )
    db.add_all(
        [
            control_task,
            AsrTask(
                session_id=session.id,
                status="completed",
                task_type="offline",
                postprocess_status="completed",
                idempotency_key=f"asr:offline:session:score-degrade:{session.id}",
            ),
            TranscriptSegment(
                session_id=session.id,
                text_content="这是用于验证评分异常降级的稳定话术终稿，完整复盘仍应继续生成。",
                segment_type="asr_offline",
                asr_status="completed",
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "app.services.tasks.batch_runners.score_session_transcript",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("评分失败")),
    )
    monkeypatch.setattr(
        "app.services.tasks.batch_runners.generate_findings", lambda *_args: []
    )
    monkeypatch.setattr(
        "app.services.tasks.batch_runners.generate_unified_review",
        lambda *_args: {"status": "completed", "analyzed_user_count": 1},
    )

    result = run_ai_review_batch(
        db,
        control_task.id,
        lambda *_args: None,
        lambda: False,
        batch_size=1,
    )

    assert result["completed_count"] == 1
    assert result["failed_count"] == 0
    assert result["warning_count"] == 1


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
