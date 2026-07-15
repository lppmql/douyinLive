import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1.monitor import start_monitor
from app.api.v1.collector import _collection_succeeded
from app.services.collector.scheduler import scheduler_manager


def test_scheduler_stop_keeps_shared_browser_alive(monkeypatch):
    closed = False

    async def fake_close():
        nonlocal closed
        closed = True

    monkeypatch.setattr("app.services.collector.scheduler.browser_manager.close", fake_close)
    asyncio.run(scheduler_manager.stop())

    assert closed is False
    assert scheduler_manager.running is False


def test_collection_completion_wakes_monitor_immediately():
    class FakeJob:
        next_run_time = None

        def modify(self, next_run_time):
            self.next_run_time = next_run_time

    class FakeScheduler:
        running = True

        def __init__(self):
            self.job = FakeJob()

        def get_job(self, _job_id):
            return self.job

    original = (
        scheduler_manager._scheduler,
        scheduler_manager._running,
        scheduler_manager._paused_for_collection,
    )
    fake_scheduler = FakeScheduler()
    try:
        scheduler_manager._scheduler = fake_scheduler
        scheduler_manager._running = True
        scheduler_manager._paused_for_collection = True

        scheduler_manager.resume_after_collection()

        assert scheduler_manager.paused_for_collection is False
        assert fake_scheduler.job.next_run_time is not None
    finally:
        (
            scheduler_manager._scheduler,
            scheduler_manager._running,
            scheduler_manager._paused_for_collection,
        ) = original


def test_monitor_can_start_while_full_collection_is_running():
    class FakeQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return SimpleNamespace(id=686)

    class FakeDb:
        def query(self, *_args):
            return FakeQuery()

    with (
        patch("app.api.v1.monitor.scheduler_manager.start", new_callable=AsyncMock) as start,
        patch("app.api.v1.monitor.browser_manager.get_logged_in_context", new_callable=AsyncMock) as login_check,
    ):
        response = asyncio.run(start_monitor(FakeDb()))

    assert response.success is True
    assert "全量采集接管" in response.message
    start.assert_awaited_once()
    login_check.assert_not_awaited()


def test_collection_waits_for_inflight_monitor_browser_job():
    async def scenario():
        scheduler_manager._active_browser_jobs = 1

        async def finish_job():
            await asyncio.sleep(0.05)
            scheduler_manager._active_browser_jobs = 0

        release = asyncio.create_task(finish_job())
        await scheduler_manager.wait_for_collection_slot(timeout_seconds=1)
        await release

    try:
        asyncio.run(scenario())
        assert scheduler_manager.paused_for_collection is True
    finally:
        scheduler_manager._active_browser_jobs = 0
        scheduler_manager._paused_for_collection = False


def test_enterprise_discovery_counts_as_success_when_root_room_page_warns():
    assert _collection_succeeded({"collected_rooms": 0, "enterprise_anchor_count": 9}) is True
    assert _collection_succeeded({"collected_rooms": 0, "enterprise_session_discovered_count": 1022}) is True
    assert _collection_succeeded({"collected_rooms": 0, "history_detail_synced_count": 20}) is True
    assert _collection_succeeded({"collected_rooms": 0}) is False


def test_realtime_browser_jobs_are_serialized():
    active_count = 0
    max_active_count = 0

    async def fake_collect(*_args):
        nonlocal active_count, max_active_count
        active_count += 1
        max_active_count = max(max_active_count, active_count)
        await asyncio.sleep(0.02)
        active_count -= 1

    async def scenario():
        with patch.object(scheduler_manager, "_collect_wrapper_serialized", side_effect=fake_collect):
            await asyncio.gather(
                scheduler_manager._collect_wrapper(13244, "https://example.test/one", "live_detail"),
                scheduler_manager._collect_wrapper(13245, "https://example.test/two", "live_detail"),
                scheduler_manager._collect_wrapper(13244, "https://example.test/one", "stream_refresh"),
            )

    asyncio.run(scenario())

    assert max_active_count == 1
