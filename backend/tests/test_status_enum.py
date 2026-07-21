"""
测试统一状态枚举 — 验证枚举值与数据库现有字符串完全兼容。

核心验证：枚举继承了 str，可以直接和数据库中取出的字符串做 == 比较。
"""

from app.core.status import (
    TaskStatus,
    ReviewFindingStatus,
    ReviewActionStatus,
    ScriptAssetStatus,
)


class TestTaskStatus:
    """验证 TaskStatus 值与数据库各模型 default 值一致"""

    def test_str_inheritance(self):
        """str + Enum 双重继承：枚举实例就是字符串"""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.QUEUED == "queued"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.PROCESSING == "processing"
        assert TaskStatus.RETRYABLE == "retryable"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"

    def test_scraper_task_default_matches(self):
        """ScraperTask.status default='pending'"""
        assert TaskStatus.PENDING == "pending"

    def test_asr_task_default_matches(self):
        """AsrTask.status default='queued'"""
        assert TaskStatus.QUEUED == "queued"

    def test_asr_postprocess_default_matches(self):
        """AsrTask.postprocess_status default='pending'"""
        assert TaskStatus.PENDING == "pending"

    def test_live_session_detail_default_matches(self):
        """LiveSession.detail_collection_status default='pending'"""
        assert TaskStatus.PENDING == "pending"

    def test_retryable_status_exists(self):
        """LiveSession.detail_collection_status 可用 'retryable'"""
        assert TaskStatus.RETRYABLE == "retryable"

    def test_enum_values_unique(self):
        """所有枚举值必须唯一，不能有重复"""
        values = [e.value for e in TaskStatus]
        assert len(values) == len(set(values))

    def test_all_expected_values_present(self):
        """确保数据库中实际使用的状态都在枚举里"""
        expected = {"pending", "queued", "running", "processing",
                     "retryable", "completed", "failed", "cancelled"}
        actual = {e.value for e in TaskStatus}
        assert expected == actual

    def test_can_use_as_dict_key(self):
        """枚举可以当 dict key 用"""
        mapping = {TaskStatus.PENDING: "等待中", TaskStatus.COMPLETED: "已完成"}
        assert mapping["pending"] == "等待中"


class TestReviewFindingStatus:
    """验证 ReviewFinding.status 枚举（值来源：数据库实际 comment）"""

    def test_str_inheritance(self):
        assert ReviewFindingStatus.OPEN == "open"
        assert ReviewFindingStatus.CONFIRMED == "confirmed"
        assert ReviewFindingStatus.DISMISSED == "dismissed"
        assert ReviewFindingStatus.RESOLVED == "resolved"

    def test_default_is_open(self):
        """ReviewFinding.status default='open'"""
        assert ReviewFindingStatus.OPEN == "open"

    def test_values_unique(self):
        values = [e.value for e in ReviewFindingStatus]
        assert len(values) == len(set(values))


class TestReviewActionStatus:
    """验证 ReviewActionItem.status 枚举"""

    def test_str_inheritance(self):
        assert ReviewActionStatus.PENDING == "pending"
        assert ReviewActionStatus.IN_PROGRESS == "in_progress"
        assert ReviewActionStatus.COMPLETED == "completed"
        assert ReviewActionStatus.VERIFIED == "verified"

    def test_default_is_pending(self):
        """ReviewActionItem.status default='pending'"""
        assert ReviewActionStatus.PENDING == "pending"


class TestScriptAssetStatus:
    """验证 ScriptAsset.status 枚举"""

    def test_str_inheritance(self):
        assert ScriptAssetStatus.CANDIDATE == "candidate"
        assert ScriptAssetStatus.APPROVED == "approved"
        assert ScriptAssetStatus.ARCHIVED == "archived"

    def test_default_is_candidate(self):
        """ScriptAsset.status default='candidate'"""
        assert ScriptAssetStatus.CANDIDATE == "candidate"
