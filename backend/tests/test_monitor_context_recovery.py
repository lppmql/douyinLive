import unittest

from app.services.collector.monitor import CluerichLiveDetector, LiveStatusResult


class FakePage:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class ClosedContext:
    async def new_page(self):
        raise RuntimeError("BrowserContext.new_page: Target page, context or browser has been closed")


class HealthyContext:
    def __init__(self):
        self.page = FakePage()

    async def new_page(self):
        return self.page


class FakeBrowserManager:
    def __init__(self):
        self.contexts = [ClosedContext(), HealthyContext()]
        self.invalidated = []

    async def get_logged_in_context(self):
        return self.contexts.pop(0), True, "ok"

    def invalidate_logged_in_context(self, context):
        self.invalidated.append(context)


class RecoveringDetector(CluerichLiveDetector):
    async def _detect_with_page(self, page, dashboard_url):
        return LiveStatusResult(is_live=True, raw_data={"url": dashboard_url})


class MonitorContextRecoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_recreates_closed_context_and_retries_once(self):
        manager = FakeBrowserManager()
        detector = RecoveringDetector(manager)

        result = await detector.detect("https://example.test/live")

        self.assertTrue(result.is_live)
        self.assertEqual(len(manager.invalidated), 1)
        self.assertTrue(manager.contexts == [])


if __name__ == "__main__":
    unittest.main()
