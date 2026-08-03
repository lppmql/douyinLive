"""直播/录播流候选与安全切换回归测试。"""

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.services.collector.stream_health import _parse_duration_seconds
from app.services.collector.stream_collector import StreamCollector


def test_recording_m3u8_wins_over_stale_live_flv():
    """页面同时出现直播 FLV 和录播 m3u8 时必须选择可定位的录播地址。"""
    selected = StreamCollector.choose_stream_candidate(
        "https://pull.example.invalid/live.flv?sign=old",
        [
            "https://pull.example.invalid/live.flv?sign=old",
            "https://record.example.invalid/third-stream-1.m3u8?sign=fresh",
        ],
    )

    assert selected == "https://record.example.invalid/third-stream-1.m3u8?sign=fresh"


def test_blob_and_non_media_requests_are_ignored():
    """浏览器 blob 和普通接口不能冒充真实转写流。"""
    selected = StreamCollector.choose_stream_candidate(
        "blob:https://dashboard.example.invalid/local-player",
        ["https://dashboard.example.invalid/api/session"],
    )

    assert selected is None


def test_parse_duration_seconds_from_ffmpeg_stderr():
    """从 ffmpeg Duration 行解析回放真实总时长（秒）。"""
    assert _parse_duration_seconds(
        "Duration: 00:48:03.61, start: 0.049000, bitrate: 0 kb/s"
    ) == pytest.approx(2883.61)
    assert _parse_duration_seconds("Duration: 01:00:00.00") == 3600.0
    assert _parse_duration_seconds("no duration here") is None
    assert _parse_duration_seconds("") is None


class _FakePage:
    def __init__(self, media_url: str):
        self.media_url = media_url
        self.request_handler = None

    def on(self, event: str, handler):
        assert event == "request"
        self.request_handler = handler

    async def goto(self, *_args, **_kwargs):
        self.request_handler(type("Request", (), {"url": self.media_url})())

    async def wait_for_timeout(self, _milliseconds: int):
        return None

    async def evaluate(self, script: str):
        if script == "navigator.userAgent":
            return "Mozilla/5.0 Test"
        return None

    async def close(self):
        return None


class _FakeContext:
    def __init__(self, page: _FakePage):
        self.page = page

    async def new_page(self):
        return self.page


class _FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def commit(self):
        return None


def test_collector_saves_unverified_stream_as_pending_with_plain_user_agent():
    """页面候选在 probe 前不能替换 active，UA 也不能多一层 JSON 引号。"""
    db = _FakeDb()
    media_url = "https://cdn.example.com/record/index.m3u8?token=fresh"
    collector = StreamCollector(db, _FakeContext(_FakePage(media_url)))

    selected = asyncio.run(collector.fetch_stream_url("https://example.com/dashboard", 42))

    assert selected == media_url
    assert len(db.added) == 1
    candidate = db.added[0]
    assert candidate.status == "pending"
    assert candidate.headers_json == {
        "User-Agent": "Mozilla/5.0 Test",
        "Referer": "https://example.com/dashboard",
    }


def _seed_stream_session(db):
    from app.models.live_rooms import LiveRoom
    from app.models.live_sessions import LiveSession
    from app.models.stream_sources import StreamSource

    room = LiveRoom(account_name="测试账号", anchor_name="测试主播")
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        dashboard_url="https://example.com/dashboard",
        stream_url="https://cdn.example.com/old.flv",
    )
    db.add(session)
    db.flush()
    old_source = StreamSource(
        session_id=session.id,
        m3u8_url=session.stream_url,
        headers_json={"User-Agent": "old"},
        status="active",
    )
    db.add(old_source)
    db.commit()
    return session, old_source


def _install_refresh_fakes(monkeypatch, alive: bool):
    from app.services.collector import stream_refresh
    from app.services.collector.browser import browser_manager

    @asynccontextmanager
    async def fake_lease(*_args, **_kwargs):
        yield

    async def fake_logged_in_context():
        return object(), True, "ok"

    async def fake_fetch(self, _dashboard_url: str, session_id: int):
        from app.models.stream_sources import StreamSource

        url = "https://cdn.example.com/record/new.m3u8"
        self.db.add(
            StreamSource(
                session_id=session_id,
                m3u8_url=url,
                headers_json={"User-Agent": "new", "Referer": "https://example.com/dashboard"},
                status="pending",
            )
        )
        self.db.commit()
        return url

    async def fake_probe(*_args, **_kwargs):
        return {"alive": alive, "error": None if alive else "404 Not Found"}

    monkeypatch.setattr(browser_manager, "session_lease", fake_lease)
    monkeypatch.setattr(browser_manager, "get_logged_in_context", fake_logged_in_context)
    monkeypatch.setattr(StreamCollector, "fetch_stream_url", fake_fetch)
    monkeypatch.setattr(stream_refresh, "probe_stream_url", fake_probe)


def test_refresh_probe_failure_preserves_previous_active_source(db, monkeypatch):
    from app.models.stream_sources import StreamSource
    from app.services.collector.stream_refresh import refresh_session_stream_url

    session, old_source = _seed_stream_session(db)
    _install_refresh_fakes(monkeypatch, alive=False)

    result = asyncio.run(refresh_session_stream_url(db, session.id))
    db.refresh(session)
    db.refresh(old_source)

    assert result["success"] is False
    assert session.stream_url == "https://cdn.example.com/old.flv"
    assert old_source.status == "active"
    candidate = db.query(StreamSource).filter(StreamSource.status == "error").one()
    assert candidate.m3u8_url.endswith("/new.m3u8")


def test_refresh_probe_success_atomically_switches_active_source(db, monkeypatch):
    from app.models.stream_sources import StreamSource
    from app.services.collector.stream_refresh import refresh_session_stream_url

    session, old_source = _seed_stream_session(db)
    _install_refresh_fakes(monkeypatch, alive=True)

    result = asyncio.run(refresh_session_stream_url(db, session.id))
    db.refresh(session)
    db.refresh(old_source)

    assert result["success"] is True
    assert session.stream_url == "https://cdn.example.com/record/new.m3u8"
    assert old_source.status == "expired"
    candidate = db.query(StreamSource).filter(StreamSource.status == "active").one()
    assert candidate.m3u8_url == session.stream_url
