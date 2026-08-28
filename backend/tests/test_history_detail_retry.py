"""历史详情失败恢复回归；所有桩数据仅位于隔离测试库，不写生产业务数据。"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.services.collector import history, room
from app.services.collector.session import (
    HISTORY_EMPTY_DETAIL_ERROR,
    HISTORY_VALIDATION_ERROR,
    _apply_session_anchor_profile,
    _needs_history_enrichment,
)
from app.services.collector.utils import _is_expected_history_session

# 采用 #2529 实际回显的起止时间作为格式回归样本，不包含账号或媒体凭证。
START = datetime(2026, 8, 28, 12, 44, 14)
END = datetime(2026, 8, 28, 14, 4, 53)
MATCHING_TEXT = "场次:\n08-28 12:44:14 ~ 08-28 14:04:53"


@pytest.mark.parametrize("error", [HISTORY_VALIDATION_ERROR, HISTORY_EMPTY_DETAIL_ERROR])
def test_known_legacy_failure_is_retryable_even_with_existing_replay(error):
    session = SimpleNamespace(
        detail_collection_status="unavailable", detail_collection_error=error,
        stream_url="https://example.invalid/replay.m3u8",
    )
    assert _needs_history_enrichment(session, has_related_assets=True)


def test_unknown_unavailable_reason_is_not_silently_requeued():
    session = SimpleNamespace(detail_collection_status="unavailable", detail_collection_error="未知原因")
    assert not _needs_history_enrichment(session)


@pytest.mark.parametrize("display_name", ["零食赛道严...-文豪", "零食赛道严…-文豪", "*******"])
def test_truncated_anchor_label_never_replaces_real_name(display_name):
    session = SimpleNamespace(
        anchor_name="零食赛道严选-文豪", anchor_nickname="零食赛道严选-文豪",
        anchor_avatar_url=None, douyin_id=None, douyin_uid=None,
    )
    assert not _apply_session_anchor_profile(session, {
        "anchor_name": display_name, "anchor_nickname": display_name,
    })
    assert session.anchor_name == session.anchor_nickname == "零食赛道严选-文豪"
    assert _apply_session_anchor_profile(session, {"douyin_id": "已核实的资料"})
    assert session.douyin_id == "已核实的资料"


def test_complete_anchor_name_can_still_be_filled():
    session = SimpleNamespace(
        anchor_name=None, anchor_nickname=None, anchor_avatar_url=None, douyin_id=None, douyin_uid=None,
    )
    assert _apply_session_anchor_profile(session, {
        "anchor_name": "零食赛道严选-文豪", "anchor_nickname": "零食赛道严选-文豪",
    })
    assert session.anchor_name == session.anchor_nickname == "零食赛道严选-文豪"


def retry_session(index, *, age_minutes=60, status="retryable"):
    return SimpleNamespace(
        id=index, anchor_name="", live_start_time=START,
        detail_collection_status=status, detail_collection_error=HISTORY_VALIDATION_ERROR,
        updated_at=datetime.utcnow() - timedelta(minutes=age_minutes),
    )


def test_retry_batch_is_bounded_and_cooling_sessions_do_not_block_new_sessions():
    retries = [retry_session(index, status="unavailable") for index in range(30)]
    cooling = retry_session(100, age_minutes=1)
    fresh = retry_session(101, age_minutes=0, status="pending")
    targets = history._order_history_enrichment_targets([cooling, *retries, fresh])
    assert targets[0] is fresh
    assert len(targets) == 1 + history.HISTORY_RETRY_BATCH_SIZE
    assert cooling not in targets


def test_retry_rotation_prefers_least_recent_attempt():
    recent = retry_session(1, age_minutes=40)
    older = retry_session(2, age_minutes=120)
    assert history._order_history_enrichment_targets([recent, older]) == [older, recent]


def test_explicit_targeting_can_retry_immediately():
    cooling = retry_session(1, age_minutes=0)
    assert history._order_history_enrichment_targets([cooling]) == []
    assert history._order_history_enrichment_targets([cooling], targeted=True) == [cooling]


@pytest.mark.parametrize("body", [
    MATCHING_TEXT,
    "场次：08-28 12:44:14 ～ 08-28 14:04:53",
    "场次:2026-08-28 12:44:14 ~ 2026-08-28 14:04:53",
])
def test_recorded_platform_time_is_accepted(body):
    assert _is_expected_history_session(body, START, END)


@pytest.mark.parametrize("body", [
    "加载中", "场次:08-28 15:38:42 ~ 08-28 16:57:57",
    "场次:08-27 12:44:14 ~ 08-27 14:04:53",
])
def test_loading_or_another_session_is_rejected(body):
    assert not _is_expected_history_session(body, START, END)


class DetailPage:
    """只模拟采集器使用的页面接口，精确控制时间文本何时到达。"""

    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.read_count = 0
        self.closed = False

    def on(self, *_args):
        pass

    async def goto(self, *_args, **_kwargs):
        pass

    async def evaluate(self, script):
        if script != "document.body?.innerText || ''":
            return False  # 没有评论标签，避免无关的点击等待。
        index = min(self.read_count, len(self.bodies) - 1)
        self.read_count += 1
        return self.bodies[index]

    async def close(self):
        self.closed = True


@pytest.mark.parametrize("delayed", [False, True])
def test_time_validation_waits_only_when_needed(monkeypatch, delayed):
    page = DetailPage(["加载中", MATCHING_TEXT] if delayed else [MATCHING_TEXT])
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    sleep = AsyncMock()
    monkeypatch.setattr(room.asyncio, "sleep", sleep)
    monkeypatch.setattr(room, "_reveal_session_anchor", AsyncMock(return_value={}))
    monkeypatch.setattr(room, "_fetch_all_session_comments", AsyncMock(return_value=([], True)))
    result = asyncio.run(room._scrape_history_session_detail(
        context, "7678938669897501503", SimpleNamespace(id=2529, live_start_time=START, live_end_time=END),
    ))
    assert not result.get("validation_failed")
    assert page.read_count == (2 if delayed else 1)
    assert [call.args[0] for call in sleep.await_args_list] == ([6, 1] if delayed else [6])
    assert page.closed


def test_wrong_session_stays_blocked_after_bounded_wait(monkeypatch):
    page = DetailPage(["场次:08-28 15:38:42 ~ 08-28 16:57:57"])
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    monkeypatch.setattr(room.asyncio, "sleep", AsyncMock())
    reveal = AsyncMock()
    monkeypatch.setattr(room, "_reveal_session_anchor", reveal)
    result = asyncio.run(room._scrape_history_session_detail(
        context, "7678938669897501503", SimpleNamespace(id=2529, live_start_time=START, live_end_time=END),
    ))
    assert result["validation_failed"]
    assert result["replay_url"] is None
    assert page.read_count == 4  # 首次读取 + 最多三次补等。
    reveal.assert_not_awaited()
    assert page.closed


def seed_history(db):
    live_room = LiveRoom(account_name="隔离测试", anchor_name="隔离测试")
    db.add(live_room)
    db.flush()
    sessions = [LiveSession(
        room_id=live_room.id, live_start_time=START, live_end_time=END,
        live_status="ended", anchor_name="隔离测试",
        dashboard_url=f"https://leads.cluerich.com/pc/analysis/live-screen?room_id={index}",
        detail_collection_status="unavailable", detail_collection_error=HISTORY_VALIDATION_ERROR,
    ) for index in (1, 2)]
    db.add_all(sessions)
    db.commit()
    return live_room, sessions


def test_targeted_retry_restores_only_selected_session_and_clears_error(db, monkeypatch):
    live_room, sessions = seed_history(db)
    scrape = AsyncMock(return_value={"overview": {"metrics": {"lp_screen_live_watch_uv": "1"}}})
    monkeypatch.setattr(history, "_scrape_history_session_detail", scrape)
    result = asyncio.run(history._enrich_history_sessions(
        db, object(), None, live_room, session_ids={sessions[0].id},
    ))
    db.expire_all()
    assert result["checked_count"] == result["enriched_count"] == 1
    assert sessions[0].detail_collection_status == "complete"
    assert sessions[0].detail_collection_error is None
    assert sessions[1].detail_collection_status == "unavailable"
    assert scrape.await_count == 1


def test_empty_scope_never_falls_back_to_all_sessions(db, monkeypatch):
    live_room, _sessions = seed_history(db)
    scrape = AsyncMock()
    monkeypatch.setattr(history, "_scrape_history_session_detail", scrape)
    result = asyncio.run(history._enrich_history_sessions(db, object(), None, live_room, session_ids=set()))
    assert result["checked_count"] == 0
    scrape.assert_not_awaited()


@pytest.mark.parametrize("detail", [
    {"validation_failed": True, "replay_url": "https://example.invalid/wrong.m3u8"},
    {"error": "页面读取失败"},
    {},
])
def test_failed_retry_preserves_saved_replay_and_refreshes_cooldown(db, monkeypatch, detail):
    live_room, sessions = seed_history(db)
    session = sessions[0]
    session.stream_url = "https://example.invalid/existing.m3u8"
    source = StreamSource(session_id=session.id, m3u8_url=session.stream_url, status="active")
    db.add(source)
    db.commit()
    monkeypatch.setattr(history, "_scrape_history_session_detail", AsyncMock(return_value=detail))
    for _ in range(2):
        session.updated_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
        result = asyncio.run(history._enrich_history_sessions(
            db, object(), None, live_room, session_ids={session.id},
        ))
        db.expire_all()
        assert result["failed_count"] == result["remaining_count"] == 1
        assert session.detail_collection_status == "retryable"
        assert session.updated_at > datetime.utcnow() - timedelta(minutes=1)
        assert session.stream_url == "https://example.invalid/existing.m3u8"
        assert source.status == "active"
        assert db.query(StreamSource).filter_by(session_id=session.id).count() == 1


def test_deferred_legacy_records_remain_visible_in_progress(db, monkeypatch):
    live_room, _sessions = seed_history(db)
    scrape = AsyncMock()
    monkeypatch.setattr(history, "_scrape_history_session_detail", scrape)
    result = asyncio.run(history._enrich_history_sessions(db, object(), None, live_room))
    assert result["checked_count"] == 0
    assert result["remaining_count"] == 2
    scrape.assert_not_awaited()
