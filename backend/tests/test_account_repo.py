"""
测试 account_repo — 采集账号数据访问层（纯 DB 操作，mock 数据库）

每个测试验证一种数据库操作场景，不依赖 Playwright 或真实浏览器。
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.services.collector.account_repo import (
    find_account_by_id,
    find_account_by_storage_path,
    find_latest_logged_in_account,
    finish_login_task,
    load_account_fingerprint,
    save_account_to_db,
    update_account_state,
)


class TestLoadAccountFingerprint:
    """load_account_fingerprint 是纯函数，不需要 mock DB"""

    def test_returns_empty_dict_for_none(self):
        assert load_account_fingerprint(None) == {}

    def test_parses_browser_fingerprint_json(self):
        account = MagicMock()
        account.browser_fingerprint_json = '{"user_agent": "test-ua", "viewport": {"width": 1280, "height": 720}}'
        result = load_account_fingerprint(account)
        assert result["user_agent"] == "test-ua"
        assert result["viewport"]["width"] == 1280

    def test_falls_back_to_legacy_fields(self):
        account = MagicMock()
        account.browser_fingerprint_json = None
        account.user_agent = "legacy-ua"
        account.viewport_width = 1024
        account.viewport_height = 768
        result = load_account_fingerprint(account)
        assert result["user_agent"] == "legacy-ua"
        assert result["viewport"]["width"] == 1024

    def test_falls_back_to_defaults_when_no_fields(self):
        account = MagicMock()
        account.browser_fingerprint_json = None
        account.user_agent = None
        account.viewport_width = None
        account.viewport_height = None
        result = load_account_fingerprint(account)
        assert result == {}

    def test_handles_invalid_json_gracefully(self):
        account = MagicMock()
        account.browser_fingerprint_json = "not-json"
        account.user_agent = "fallback-ua"
        account.viewport_width = 800
        account.viewport_height = 600
        result = load_account_fingerprint(account)
        assert result["user_agent"] == "fallback-ua"


class TestFindAccountById:
    """测试按 ID 查找账号"""

    def test_returns_none_for_none_id(self):
        db = MagicMock(spec=Session)
        assert find_account_by_id(db, None) is None

    def test_delegates_to_db_get(self):
        db = MagicMock(spec=Session)
        mock_account = MagicMock()
        db.get.return_value = mock_account
        result = find_account_by_id(db, 42)
        db.get.assert_called_once()
        assert result is mock_account


class TestFindAccountByStoragePath:
    """测试按 storage_state_path 查找账号"""

    def test_returns_none_for_empty_path(self):
        db = MagicMock(spec=Session)
        assert find_account_by_storage_path(db, None) is None
        assert find_account_by_storage_path(db, "") is None

    def test_queries_by_storage_path(self):
        db = MagicMock(spec=Session)
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_filter = MagicMock()
        mock_query.filter.return_value = mock_filter
        mock_order = MagicMock()
        mock_filter.order_by.return_value = mock_order
        mock_account = MagicMock()
        mock_order.first.return_value = mock_account

        result = find_account_by_storage_path(db, "/path/to/state.json")
        assert result is mock_account


class TestFindLatestLoggedInAccount:
    """测试查找最近登录的账号"""

    def test_queries_logged_in_accounts(self):
        db = MagicMock(spec=Session)
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_filter = MagicMock()
        mock_query.filter.return_value = mock_filter
        mock_order = MagicMock()
        mock_filter.order_by.return_value = mock_order
        mock_account = MagicMock(id=1)
        mock_order.first.return_value = mock_account

        result = find_latest_logged_in_account(db)
        assert result is mock_account


class TestUpdateAccountState:
    """测试更新账号状态"""

    def test_noop_for_none_account_id(self):
        db = MagicMock(spec=Session)
        update_account_state(db, None)  # 不应报错
        db.query.assert_not_called()

    def test_noop_when_account_not_found(self):
        db = MagicMock(spec=Session)
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.get.return_value = None
        update_account_state(db, 1, storage_path="/path")
        db.flush.assert_not_called()

    def test_updates_storage_path(self):
        db = MagicMock(spec=Session)
        account = MagicMock()
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.get.return_value = account

        update_account_state(db, 1, storage_path="/new/path.json")
        assert account.storage_state_path == "/new/path.json"

    def test_updates_cookies(self):
        db = MagicMock(spec=Session)
        account = MagicMock()
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.get.return_value = account

        update_account_state(db, 1, cookies_json='{"key": "val"}')
        assert account.cookies_json == '{"key": "val"}'


class TestSaveAccountToDb:
    """测试保存账号到数据库"""

    @patch("app.services.collector.account_repo.ScraperAccount")
    def test_creates_new_account(self, mock_scraper_cls):
        """新建账号时，ScraperAccount 实例应该有 id"""
        db = MagicMock(spec=Session)
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.get.return_value = None
        mock_filter = MagicMock()
        mock_query.filter.return_value = mock_filter
        mock_filter.order_by.return_value = mock_filter
        mock_filter.first.return_value = None

        # 让新建的 ScraperAccount 实例有 id
        mock_account = MagicMock()
        mock_account.id = 99
        mock_scraper_cls.return_value = mock_account

        result = save_account_to_db(
            db, task_id=100, account_name="test_account",
            storage_path="/path", cookies_json="{}",
            browser_fingerprint_json="{}",
            ua="test-ua", vp_width=1920, vp_height=1080,
        )
        db.add.assert_called_once()
        db.flush.assert_called()
        assert result == 99

    def test_updates_existing_account(self):
        db = MagicMock(spec=Session)
        existing = MagicMock()
        existing.id = 5
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.get.return_value = existing

        result = save_account_to_db(
            db, task_id=100, account_name="existing",
            storage_path="/path", cookies_json="{}",
            browser_fingerprint_json="{}",
            ua="ua", vp_width=800, vp_height=600,
            account_id=5,
        )
        assert existing.login_status == "logged_in"
        assert existing.storage_state_path == "/path"
        assert result == 5


class TestFinishLoginTask:
    """测试结束登录任务"""

    def test_noop_when_task_not_found(self):
        db = MagicMock(spec=Session)
        db.get.return_value = None
        finish_login_task(db, 1, "failed", "error")
        db.flush.assert_not_called()

    def test_noop_when_task_already_completed(self):
        db = MagicMock(spec=Session)
        task = MagicMock()
        task.status = "completed"
        db.get.return_value = task
        finish_login_task(db, 1, "completed")
        db.flush.assert_not_called()

    def test_sets_failed_status(self):
        db = MagicMock(spec=Session)
        task = MagicMock()
        task.status = "running"
        db.get.return_value = task
        finish_login_task(db, 1, "failed", "登录超时")
        assert task.status == "failed"
        assert task.error_message == "登录超时"
        db.flush.assert_called_once()
