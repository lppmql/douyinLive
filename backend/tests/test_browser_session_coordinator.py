import asyncio

from app.services.collector.browser import BrowserManager
from app.services.collector.browser_session import BrowserSessionCoordinator


def test_refresh_waiter_has_priority_over_later_monitor_jobs():
    """刷新一旦等待接管，后来的监控不能插队或与它重叠。"""

    async def scenario():
        coordinator = BrowserSessionCoordinator()
        first_monitor_entered = asyncio.Event()
        release_first_monitor = asyncio.Event()
        refresh_entered = asyncio.Event()
        release_refresh = asyncio.Event()
        execution_order: list[str] = []
        active_count = 0
        max_active_count = 0

        async def run_job(owner: str, kind: str, entered: asyncio.Event, release: asyncio.Event):
            nonlocal active_count, max_active_count
            async with coordinator.lease(owner, kind=kind):
                active_count += 1
                max_active_count = max(max_active_count, active_count)
                execution_order.append(owner)
                entered.set()
                await release.wait()
                active_count -= 1

        first_monitor = asyncio.create_task(
            run_job("monitor:first", "monitor", first_monitor_entered, release_first_monitor)
        )
        await first_monitor_entered.wait()

        refresh = asyncio.create_task(
            run_job("refresh", "refresh", refresh_entered, release_refresh)
        )
        await coordinator.wait_for_refresh_waiter(timeout_seconds=1)

        second_monitor_entered = asyncio.Event()
        release_second_monitor = asyncio.Event()
        second_monitor = asyncio.create_task(
            run_job("monitor:second", "monitor", second_monitor_entered, release_second_monitor)
        )

        release_first_monitor.set()
        await refresh_entered.wait()
        assert second_monitor_entered.is_set() is False

        release_refresh.set()
        await second_monitor_entered.wait()
        release_second_monitor.set()
        await asyncio.gather(first_monitor, refresh, second_monitor)

        return execution_order, max_active_count, coordinator.snapshot()

    order, max_active, snapshot = asyncio.run(scenario())

    assert order == ["monitor:first", "refresh", "monitor:second"]
    assert max_active == 1
    assert snapshot["active_owner"] is None
    assert snapshot["waiting_refresh"] == 0


def test_cancelled_refresh_waiter_does_not_block_monitor_queue():
    """等待中的刷新被停止后，必须唤醒监控，不能留下永久锁。"""

    async def scenario():
        coordinator = BrowserSessionCoordinator()
        monitor_release = asyncio.Event()
        monitor_entered = asyncio.Event()

        async def hold_monitor():
            async with coordinator.lease("monitor:first", kind="monitor"):
                monitor_entered.set()
                await monitor_release.wait()

        first_monitor = asyncio.create_task(hold_monitor())
        await monitor_entered.wait()

        async def wait_refresh():
            async with coordinator.lease("refresh", kind="refresh"):
                return None

        refresh = asyncio.create_task(wait_refresh())
        await coordinator.wait_for_refresh_waiter(timeout_seconds=1)
        refresh.cancel()
        await asyncio.gather(refresh, return_exceptions=True)

        monitor_release.set()
        await first_monitor
        async def run_second_monitor():
            async with coordinator.lease("monitor:second", kind="monitor"):
                return None

        await asyncio.wait_for(run_second_monitor(), timeout=1)
        return coordinator.snapshot()

    snapshot = asyncio.run(scenario())

    assert snapshot["waiting_refresh"] == 0
    assert snapshot["active_owner"] is None


def test_browser_shutdown_closes_pages_contexts_and_driver_in_order():
    """停机必须逐层收尾，不能直接切断仍有响应回调的 Playwright 驱动。"""

    async def scenario():
        close_order: list[str] = []

        class FakePage:
            async def close(self, *, run_before_unload: bool):
                assert run_before_unload is False
                close_order.append("page")

        class FakeContext:
            pages = [FakePage()]

            async def close(self):
                close_order.append("context")

        class FakeBrowser:
            contexts = [FakeContext()]

            def is_connected(self):
                return True

            async def close(self):
                close_order.append("browser")

        class FakePlaywright:
            async def stop(self):
                close_order.append("playwright")

        manager = BrowserManager()
        manager._session_coordinator = BrowserSessionCoordinator()
        manager._browser = FakeBrowser()
        manager._playwright = FakePlaywright()
        manager._logged_in_context = manager._browser.contexts[0]
        manager._logged_in_account_id = 6
        manager._logged_in_storage_path = "/tmp/storage-state.json"

        await manager.close()
        return close_order, manager

    order, manager = asyncio.run(scenario())

    assert order == ["page", "context", "playwright"]
    assert manager._browser is None
    assert manager._playwright is None
    assert manager._logged_in_context is None
