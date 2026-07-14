from unittest.mock import Mock, patch

from app.api.v1.dataease import _coverage
from app.services.sync.analysis_sync import _score_value
from app.services.sync.de_sync import sync_sessions


def test_coverage_counts_missing_and_outdated_sessions():
    fresh, pending, rate = _coverage(source_count=20, synced_count=15, outdated_count=2)

    assert fresh == 13
    assert pending == 7
    assert rate == 65.0


def test_score_value_ignores_invalid_ai_output():
    assert _score_value({"total_score": "8.5"}, "total_score") == 8.5
    assert _score_value({"total_score": "未知"}, "total_score") is None
    assert _score_value(None, "total_score") is None


def test_sync_sessions_keeps_other_sessions_when_one_fails():
    db = Mock()
    with patch(
        "app.services.sync.de_sync.sync_session",
        side_effect=[None, RuntimeError("bad row"), None],
    ):
        result = sync_sessions(db, [11, 12, 13])

    assert result["selected_count"] == 3
    assert result["synced_count"] == 2
    assert result["failed_count"] == 1
    assert result["errors"] == [{"session_id": 12, "message": "bad row"}]
    db.rollback.assert_called_once()
