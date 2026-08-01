"""全新数据库必须复用已登录账号自动发现根直播间。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.models.live_rooms import LiveRoom
from app.models.scraper_accounts import ScraperAccount
from app.services.collector.manual_collect import _save_discovered_root_room
from app.services.collector.room import discover_root_room_id


def test_discovers_room_id_from_enterprise_redirect():
    page = SimpleNamespace(
        url="https://leads.cluerich.com/pc/analysis/live-comment?roomId=7668184469272136494",
        goto=AsyncMock(),
        wait_for_timeout=AsyncMock(),
        close=AsyncMock(),
    )
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))

    room_id = asyncio.run(discover_root_room_id(context))

    assert room_id == "7668184469272136494"
    page.goto.assert_awaited_once()
    page.close.assert_awaited_once()


def test_saves_discovered_room_idempotently(db):
    account = ScraperAccount(
        account_name="采集账号",
        douyin_nickname="真实昵称",
        douyin_id="douyin-account",
        login_status="logged_in",
    )
    db.add(account)
    db.commit()

    first = _save_discovered_root_room(db, account, "7668184469272136494")
    second = _save_discovered_root_room(db, account, "7668184469272136494")

    assert first.id == second.id
    assert first.anchor_name == "真实昵称"
    assert first.douyin_id == "douyin-account"
    assert db.query(LiveRoom).count() == 1
