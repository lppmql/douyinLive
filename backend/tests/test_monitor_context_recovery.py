import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.services.collector.browser import BrowserManager
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

    async def test_restores_saved_account_reference_after_process_restart(self):
        manager = BrowserManager()
        original = (
            manager._logged_in_context,
            manager._logged_in_account_id,
            manager._logged_in_storage_path,
        )
        with TemporaryDirectory() as directory:
            storage_path = Path(directory) / "state.json"
            storage_path.write_text("{}", encoding="utf-8")
            account = SimpleNamespace(
                id=7,
                storage_state_path=str(storage_path),
                browser_fingerprint_json=None,
                user_agent=None,
                viewport_width=None,
                viewport_height=None,
            )
            manager._logged_in_context = None
            manager._logged_in_account_id = None
            manager._logged_in_storage_path = None

            with (
                patch.object(manager, "_find_latest_logged_in_account", return_value=account),
                patch.object(manager, "_find_account_by_id", return_value=account),
                patch.object(manager, "create_context", return_value=None) as create_context,
            ):
                create_context.return_value = FakeAsyncContext()
                with patch.object(manager, "check_login_expired", return_value=False):
                    context, valid, _message = await manager.get_logged_in_context()

            self.assertTrue(valid)
            self.assertIsNotNone(context)
            self.assertEqual(manager._logged_in_account_id, 7)
            self.assertEqual(manager._logged_in_storage_path, str(storage_path))

        manager._logged_in_context, manager._logged_in_account_id, manager._logged_in_storage_path = original


class FakeAsyncContext:
    async def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
