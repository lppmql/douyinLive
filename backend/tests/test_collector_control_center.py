"""数据采集控制中心的关键回归测试。"""

from datetime import datetime

from app.core.status import TaskStatus
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.collector_module_states import CollectorModuleState
from app.models.scraper_logs import ScraperLog
from app.models.scraper_tasks import ScraperTask
from app.schemas.scraper import CollectorControlCenterResponse
from app.services.collector.account_identity import parse_account_identity
from app.services.collector.log_service import sanitize_log_data
from app.services.tasks.control import CollectorTaskControlManager
from app.services.tasks.status import build_control_center
from app.services.tasks.views import serialize_scraper_task


def test_parse_account_identity_only_uses_verified_user_fields():
    payload = {
        "error_code": 0,
        "data": {
            "nick_name": "  真实扫码昵称  ",
            "douyin_unique_id": " 123456789 ",
            "company_name": "不能误当成昵称",
        },
    }

    assert parse_account_identity(payload) == {
        "douyin_nickname": "真实扫码昵称",
        "douyin_id": "123456789",
    }
    assert parse_account_identity({"error_code": 1001, "data": payload["data"]}) == {
        "douyin_nickname": None,
        "douyin_id": None,
    }


def test_sanitize_log_data_hides_credentials_and_limits_large_lists():
    payload = {
        "comment_count": 18,
        "cookie": "secret-cookie",
        "nested": {
            "Authorization": "Bearer secret-token",
            "m3u8_url": "https://secret.example/live.m3u8",
            "visible": "保留我",
        },
        "items": list(range(25)),
    }

    result = sanitize_log_data(payload)

    assert result["comment_count"] == 18
    assert "cookie" not in result
    assert result["nested"] == {"visible": "保留我"}
    assert result["items"][-1] == {"omitted_count": 5}


def test_scraper_task_view_exposes_stop_retry_and_real_progress():
    now = datetime.utcnow()
    task = ScraperTask(
        id=42,
        task_type="collect_all",
        status=TaskStatus.RUNNING,
        progress_percent=65,
        progress_current=13,
        progress_total=20,
        progress_stage="detail_enrichment",
        progress_message="已检查 13/20 场",
        collected_anchor_count=9,
        collected_session_count=20,
        checked_detail_count=13,
        refreshed_detail_count=7,
        failed_detail_count=1,
        remaining_detail_count=7,
        retry_count=1,
        max_retries=2,
        created_at=now,
        updated_at=now,
    )

    payload = serialize_scraper_task(task)

    assert payload["task_key"] == "scraper:42"
    assert payload["can_stop"] is True
    assert payload["can_retry"] is False
    assert payload["collected_anchor_count"] == 9
    assert payload["collected_session_count"] == 20
    assert payload["refreshed_detail_count"] == 7


def test_task_manager_safely_stops_pending_task_and_marks_it_retryable(db, monkeypatch):
    import app.services.tasks.control as control_module
    from conftest import TestSessionLocal

    monkeypatch.setattr(control_module, "SessionLocal", TestSessionLocal)
    original = ScraperTask(
        id=101,
        task_type="knowledge_sync",
        status=TaskStatus.PENDING,
        progress_stage="queued",
        progress_message="等待执行",
        task_options_json={"scope": "pending"},
    )
    db.add(original)
    db.commit()
    db.refresh(original)

    manager = CollectorTaskControlManager()
    stopped = manager.request_cancel(original.id)

    assert stopped.status == TaskStatus.CANCELLED
    assert stopped.cancel_requested_at is not None
    assert serialize_scraper_task(stopped)["can_retry"] is True


def test_logs_endpoint_enriches_anchor_and_session_without_exposing_secrets(client, db, auth_headers):
    room = LiveRoom(
        account_name="真实企业账号",
        anchor_name="测试主播",
        room_id_str="room-1001",
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        session_title="零食店避坑直播",
        anchor_name="测试主播",
        live_start_time=datetime.utcnow(),
    )
    db.add(session)
    db.flush()
    task = ScraperTask(
        id=102,
        session_id=session.id,
        task_type="collect_all",
        status=TaskStatus.COMPLETED,
        progress_percent=100,
    )
    db.add(task)
    db.flush()
    db.add(
        ScraperLog(
            id=103,
            task_id=task.id,
            level="info",
            message="评论采集完成",
            raw_json={
                "session_id": session.id,
                "stage": "detail_enrichment",
                "details": {
                    "comment_count": 18,
                    "cookie": "secret-cookie",
                    "m3u8_url": "https://secret.example/live.m3u8",
                },
            },
        )
    )
    db.commit()

    response = client.get("/api/v1/collector/logs", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["anchor_name"] == "测试主播"
    assert payload["session_title"] == "零食店避坑直播"
    assert payload["room_id_str"] == "room-1001"
    assert payload["data_details"] == {"comment_count": 18}
    assert "secret-cookie" not in response.text
    assert "secret.example" not in response.text


def test_task_action_payload_ends_old_transaction_before_reading_task(monkeypatch):
    import app.api.v1.collector as collector_api

    events: list[str] = []

    class FakeDb:
        def commit(self):
            events.append("commit")

        def expire_all(self):
            events.append("expire_all")

    def fake_get_unified_task(db, source, task_id):
        assert events == ["commit", "expire_all"]
        return {"source": source, "id": task_id}

    monkeypatch.setattr(collector_api, "get_unified_task", fake_get_unified_task)

    result = collector_api._task_action_payload(FakeDb(), "scraper", 108, "任务已加入队列")

    assert result == {
        "success": True,
        "message": "任务已加入队列",
        "task": {"source": "scraper", "id": 108},
    }


def test_control_center_converts_empty_module_errors_to_contract_strings(db):
    db.add(
        CollectorModuleState(
            module_key="asr",
            enabled=True,
            interval_seconds=5,
            last_error=None,
        )
    )
    db.commit()
    resource_usage = {
        "sampled_at": datetime.utcnow(),
        "cpu_percent": 12.5,
        "memory_percent": 66.0,
        "memory_used_bytes": 1,
        "memory_total_bytes": 2,
        "disk_used_percent": 30.0,
        "disk_free_bytes": 3,
        "app_memory_bytes": 1,
        "pressure_level": "normal",
        "pressure_message": "资源正常",
        "components": [],
    }

    payload = build_control_center(
        db,
        {"enabled": False, "engine_running": False, "worker_running": False},
        resource_usage,
    )
    validated = CollectorControlCenterResponse.model_validate(payload)

    asr_module = next(item for item in validated.modules if item.key == "asr")
    assert asr_module.disabled_reason == ""
