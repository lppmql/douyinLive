import unittest
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.services.collector.browser import BROWSER_ARGS, BROWSER_CHANNEL, BrowserManager
from app.services.collector.monitor import CluerichLiveDetector, LiveStatusResult
from app.services.collector.manual_collect import _is_context_closed_message, _sanitize_collector_error


class FakePage:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class ContextClosedMessageTest(unittest.TestCase):
    def test_recognizes_context_closed_collection_result(self):
        self.assertTrue(_is_context_closed_message(
            "BrowserContext.new_page: Target page, context or browser has been closed"
        ))
        self.assertFalse(_is_context_closed_message("登录已过期，请重新扫码"))

    def test_sanitizes_playwright_browser_logs(self):
        raw_error = (
            "BrowserContext.new_page: Target page, context or browser has been closed\n"
            "Browser logs:\n" + "EGL Driver message (Error) " * 1000
        )

        compact = _sanitize_collector_error(raw_error)

        self.assertEqual(compact, "浏览器进程意外退出（Target page, context or browser has been closed）")
        self.assertNotIn("EGL Driver", compact)
        self.assertLessEqual(len(compact), 500)

    def test_browser_disables_graphics_acceleration(self):
        self.assertEqual(BROWSER_CHANNEL, "chromium")
        self.assertIn("--disable-gpu", BROWSER_ARGS)
        self.assertIn("--disable-webgl", BROWSER_ARGS)
        self.assertNotIn("--disable-software-rasterizer", BROWSER_ARGS)


class ClosedContext:
    async def new_page(self):
        raise RuntimeError("BrowserContext.new_page: Target page, context or browser has been closed")


class HealthyContext:
    def __init__(self):
        self.page = FakePage()

    async def new_page(self):
        return self.page


class ContextWithPageCounter:
    def __init__(self):
        self.page_count = 0

    async def add_init_script(self, _script):
        return None

    async def new_page(self):
        self.page_count += 1
        return FakePage()


class BrowserWithContextCounter:
    def __init__(self, context):
        self.context = context

    async def new_context(self, **_options):
        return self.context


class LoginCheckPage(FakePage):
    def __init__(self, url, body):
        super().__init__()
        self.url = url
        self.body = body

    async def goto(self, *_args, **_kwargs):
        return None

    async def evaluate(self, _script):
        return self.body


class LoginCheckContext:
    def __init__(self, pages):
        self.pages = list(pages)

    async def new_page(self):
        return self.pages.pop(0)


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
    async def test_create_context_keeps_one_blank_page_alive(self):
        manager = BrowserManager()
        context = ContextWithPageCounter()
        with patch.object(manager, "ensure_browser", return_value=BrowserWithContextCounter(context)):
            result = await manager.create_context()

        self.assertIs(result, context)
        self.assertEqual(context.page_count, 1)

    async def test_serializes_logged_in_context_recovery(self):
        manager = BrowserManager()
        active_calls = 0
        max_active_calls = 0

        async def fake_get_context():
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            await asyncio.sleep(0.01)
            active_calls -= 1
            return HealthyContext(), True, "ok"

        with patch.object(manager, "_get_logged_in_context_unlocked", side_effect=fake_get_context):
            await asyncio.gather(manager.get_logged_in_context(), manager.get_logged_in_context())

        self.assertEqual(max_active_calls, 1)

    async def test_login_expiry_requires_two_consecutive_failures(self):
        manager = BrowserManager()
        pages = [
            LoginCheckPage("https://leads.cluerich.com/pc/auth/login", "手机登录"),
            LoginCheckPage("https://leads.cluerich.com/pc/analysis/live-screen", "直播数据"),
        ]

        with patch("app.services.collector.browser.asyncio.sleep", return_value=None):
            expired = await manager.check_login_expired(LoginCheckContext(pages))

        self.assertFalse(expired)
        self.assertTrue(all(page.closed for page in pages))

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
