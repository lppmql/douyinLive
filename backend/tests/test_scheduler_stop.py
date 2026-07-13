import asyncio

from app.services.collector.scheduler import scheduler_manager


def test_scheduler_stop_releases_browser(monkeypatch):
    closed = False

    async def fake_close():
        nonlocal closed
        closed = True

    monkeypatch.setattr("app.services.collector.scheduler.browser_manager.close", fake_close)
    asyncio.run(scheduler_manager.stop())

    assert closed is True
    assert scheduler_manager.running is False
