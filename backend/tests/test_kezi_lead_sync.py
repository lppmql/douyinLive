"""客资增量同步的契约、去重和场次归属测试。"""

import asyncio
from datetime import datetime

import pytest

from app.api.v1.leads import attribute_lead, create_lead, delete_lead
from app.core.config import is_valid_kezi_api_key
from app.models.lead_sync_states import LeadSyncState
from app.models.leads import Lead
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.schemas import LeadCreate
from app.schemas.leads import LeadAttributionUpdate
from app.services.leads.kezi_sync import (
    KeziLeadItem,
    KeziLeadPage,
    KeziSyncError,
    match_live_session,
    sync_kezi_leads,
    validate_page_cursor,
)


def test_kezi_item_requires_real_source_id():
    """没有源系统唯一编号的数据不能入库，否则无法可靠去重。"""
    try:
        KeziLeadItem.model_validate(
            {
                "phone": "13800138000",
                "douyinId": "douyin-test",
                "anchor": "主播甲",
                "createdAt": "2026-07-27T10:30:00",
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("缺少 sourceId 的客资不应通过校验")


def test_kezi_item_clears_only_oversized_douyin_id():
    """上游异常长身份值不能阻塞整页，也不能截断后冒充真实抖音号。"""
    item = KeziLeadItem.model_validate(
        {
            "sourceId": 99,
            "phone": "13800138000",
            "douyinId": "x" * 166,
            "anchor": "主播甲",
            "createdAt": "2026-09-02T10:30:00",
        }
    )

    assert item.douyin_id == ""
    assert item.douyin_id_sanitized is True
    assert item.phone == "13800138000"
    assert item.anchor == "主播甲"
    assert "douyin_id_sanitized" not in item.model_dump()


def test_kezi_key_rejects_long_chinese_placeholder():
    """中文占位内容即使超过 32 位也不能放进 HTTP 请求头冒充真实密钥。"""
    assert is_valid_kezi_api_key("read-key-abcdefghijklmnopqrstuvwxyz-123456")
    assert not is_valid_kezi_api_key("这是一个很长但不能用于请求头的中文占位密钥" * 2)


def test_match_live_session_by_anchor_and_real_time(db):
    """只把客资归到同主播且时间覆盖提交时刻的真实场次。"""
    room = LiveRoom(
        room_id_str="room-kezi-test",
        account_name="客资测试账号",
        anchor_name="主播甲",
        platform="douyin",
        status=True,
    )
    db.add(room)
    db.flush()
    matched = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 10, 0),
        live_end_time=datetime(2026, 7, 27, 11, 0),
    )
    other_anchor = LiveSession(
        room_id=room.id,
        anchor_name="主播乙",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 10, 0),
        live_end_time=datetime(2026, 7, 27, 11, 0),
    )
    db.add_all([matched, other_anchor])
    db.commit()

    item = KeziLeadItem(
        sourceId=101,
        phone="13800138000",
        douyinId="douyin-test",
        anchor="主播甲",
        createdAt=datetime(2026, 7, 27, 10, 30),
    )

    session, reason = match_live_session(db, item)
    assert session is not None
    assert session.id == matched.id
    assert reason == "time_window"


def test_unmatched_lead_stays_pending_instead_of_faking_session(db):
    """没有匹配场次时必须进入待归属，不能猜一个场次。"""
    item = KeziLeadItem(
        sourceId=102,
        phone="",
        douyinId="douyin-unmatched",
        anchor="不存在的主播",
        createdAt=datetime(2026, 7, 27, 10, 30),
    )

    session, _ = match_live_session(db, item)
    assert session is None


def test_overlapping_sessions_pick_closest_by_proximity(db):
    """同主播两个重叠场次都覆盖时间时，选客资最接近结束时间的那场。"""
    room = LiveRoom(
        room_id_str="room-ambiguous-test",
        account_name="歧义测试账号",
        anchor_name="主播甲",
        platform="douyin",
        status=True,
    )
    db.add(room)
    db.flush()
    # 场次 10:00-11:00（客资距结束 30min） vs 10:15-10:45（客资距结束 15min）
    session_long = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 10, 0),
        live_end_time=datetime(2026, 7, 27, 11, 0),
    )
    session_short = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 10, 15),
        live_end_time=datetime(2026, 7, 27, 10, 45),
    )
    db.add_all([session_long, session_short])
    db.commit()
    item = KeziLeadItem(
        sourceId=103,
        phone="",
        douyinId="douyin-ambiguous",
        anchor="主播甲",
        createdAt=datetime(2026, 7, 27, 10, 30),
    )

    session, reason = match_live_session(db, item)
    assert session is not None
    # 应该选 session_short：客资距其结束只有 15 分钟，比长场次更接近
    assert session.id == session_short.id
    assert reason == "time_window"


def test_multiple_overlapping_sessions_pick_best_match(db):
    """即使重叠场次很多，也能按客资在直播时段内的距离选最佳场次。"""
    room = LiveRoom(
        room_id_str="room-many-ambiguous-test",
        account_name="多场次歧义测试账号",
        anchor_name="主播甲",
        platform="douyin",
        status=True,
    )
    db.add(room)
    db.flush()
    # 两个长场次都覆盖 10:30；中间插入的短场次用于复现旧版 limit(10) 漏查。
    wide = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 8, 0),
        live_end_time=datetime(2026, 7, 27, 12, 0),
    )
    narrow = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 9, 0),
        live_end_time=datetime(2026, 7, 27, 11, 0),
    )
    db.add_all(
        [
            wide,
            narrow,
            *[
                LiveSession(
                    room_id=room.id,
                    anchor_name="主播甲",
                    live_status="ended",
                    live_start_time=datetime(2026, 7, 27, 10, minute),
                    live_end_time=datetime(2026, 7, 27, 10, minute + 1),
                )
                for minute in range(1, 12)
            ],
        ]
    )
    db.commit()

    item = KeziLeadItem(
        sourceId=104,
        phone="",
        douyinId="douyin-many-ambiguous",
        anchor="主播甲",
        createdAt=datetime(2026, 7, 27, 10, 30),
    )

    session, reason = match_live_session(db, item)
    assert session is not None
    # narrow (09:00-11:00): 客资 10:30 距结束 30min
    # wide (08:00-12:00): 客资 10:30 距结束 90min
    # 应选 narrow（距结束更近）
    assert session.id == narrow.id
    assert reason == "time_window"


def test_incremental_sync_persists_cursor_and_deduplicates(db, monkeypatch):
    """同步成功后保存游标；再次执行不会重复插入同一条真实客资。"""
    room = LiveRoom(
        room_id_str="room-sync-test",
        account_name="客资同步账号",
        anchor_name="主播甲",
        platform="douyin",
        status=True,
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 10, 0),
        live_end_time=datetime(2026, 7, 27, 11, 0),
    )
    db.add(session)
    db.commit()

    class FakeClient:
        async def fetch_page(self, last_id: int, limit: int) -> KeziLeadPage:
            assert limit == 100
            if last_id >= 201:
                return KeziLeadPage(lastId=last_id, count=0, hasMore=False, data=[])
            return KeziLeadPage(
                lastId=201,
                count=1,
                hasMore=False,
                data=[
                    {
                        "sourceId": 201,
                        "phone": "13800138000",
                        "douyinId": "douyin-real",
                        "anchor": "主播甲",
                        "createdAt": "2026-07-27T10:30:00",
                    }
                ],
            )

    monkeypatch.setattr("app.services.leads.kezi_sync.settings.KEZI_SYNC_PAGE_SIZE", 100)
    first = asyncio.run(sync_kezi_leads(db, client=FakeClient()))
    second = asyncio.run(sync_kezi_leads(db, client=FakeClient()))

    state = db.query(LeadSyncState).one()
    lead = db.query(Lead).one()
    db.refresh(session)
    assert first["added_count"] == 1
    assert second["added_count"] == 0
    assert state.last_external_id == 201
    assert state.synced_count == 1
    assert lead.session_id == session.id
    assert lead.external_id == 201
    assert session.leads_count == 1


def test_incremental_sync_keeps_lead_and_advances_cursor_when_douyin_id_is_oversized(
    db, monkeypatch
):
    """单个异常抖音号只降级身份字段，真实客资和增量游标仍要保存。"""

    class FakeClient:
        async def fetch_page(self, last_id: int, limit: int) -> KeziLeadPage:
            del limit
            return KeziLeadPage(
                lastId=last_id + 1,
                count=1,
                hasMore=False,
                data=[
                    {
                        "sourceId": last_id + 1,
                        "phone": "13800138000",
                        "douyinId": "x" * 166,
                        "anchor": "暂无真实场次主播",
                        "createdAt": "2026-09-02T10:30:00",
                    }
                ],
            )

    monkeypatch.setattr("app.services.leads.kezi_sync.settings.KEZI_SYNC_PAGE_SIZE", 100)
    result = asyncio.run(sync_kezi_leads(db, client=FakeClient()))

    state = db.query(LeadSyncState).one()
    lead = db.query(Lead).one()
    assert result["added_count"] == 1
    assert result["sanitized_douyin_id_count"] == 1
    assert state.last_external_id == 1
    assert lead.external_id == 1
    assert lead.lead_phone == "13800138000"
    assert lead.douyin_id is None


def test_page_cursor_rejects_old_or_out_of_order_source_ids():
    """上游乱序或倒退时整页失败，游标不能越过尚未可靠保存的数据。"""
    page = KeziLeadPage(
        lastId=302,
        count=2,
        hasMore=False,
        data=[
            {
                "sourceId": 302,
                "phone": "",
                "douyinId": "first",
                "anchor": "主播",
                "createdAt": "2026-07-27T10:30:00",
            },
            {
                "sourceId": 301,
                "phone": "",
                "douyinId": "second",
                "anchor": "主播",
                "createdAt": "2026-07-27T10:31:00",
            },
        ],
    )

    with pytest.raises(KeziSyncError, match="严格递增"):
        validate_page_cursor(page, 300)


def test_internal_sync_error_never_persists_customer_pii(db):
    """数据库或第三方异常即使带原始参数，状态接口也只能保存安全提示。"""
    class LeakyClient:
        async def fetch_page(self, last_id: int, limit: int) -> KeziLeadPage:
            del last_id, limit
            raise ValueError("SQL params: 13800138000, douyin-secret")

    with pytest.raises(KeziSyncError) as error:
        asyncio.run(sync_kezi_leads(db, client=LeakyClient()))

    state = db.query(LeadSyncState).one()
    assert "13800138000" not in str(error.value)
    assert "douyin-secret" not in str(error.value)
    assert "13800138000" not in state.last_error
    assert "douyin-secret" not in state.last_error


def test_manual_create_cannot_spoof_external_source_identity():
    """人工接口不能伪造 kezi 的 sourceId 绕过去重规则。"""
    with pytest.raises(ValueError):
        LeadCreate.model_validate(
            {
                "session_id": 1,
                "lead_phone": "13800138000",
                "external_source": "kezi",
                "external_id": 999,
            }
        )


def test_manual_attribution_refreshes_old_and_new_session_counts(db):
    """客资改绑场次后，旧场次要减一，新场次要加一。"""
    room = LiveRoom(
        room_id_str="room-attribution-test",
        account_name="归属测试账号",
        anchor_name="主播甲",
        platform="douyin",
        status=True,
    )
    db.add(room)
    db.flush()
    old_session = LiveSession(room_id=room.id, anchor_name="主播甲", live_status="ended")
    new_session = LiveSession(room_id=room.id, anchor_name="主播乙", live_status="ended")
    db.add_all([old_session, new_session])
    db.flush()
    lead = Lead(
        session_id=old_session.id,
        lead_phone="13800138000",
        douyin_id="confirmed-user",
        anchor_name="主播甲",
        create_time=datetime(2026, 8, 1, 10, 0),
        is_valid=1,
    )
    db.add(lead)
    old_session.leads_count = 1
    new_session.leads_count = 0
    db.commit()

    attribute_lead(
        lead.id,
        LeadAttributionUpdate(session_id=new_session.id),
        db=db,
    )
    db.refresh(old_session)
    db.refresh(new_session)

    assert old_session.leads_count == 0
    assert new_session.leads_count == 1


def test_manual_create_and_delete_refresh_session_count(db):
    """人工新增和删除客资后，看板场次数量必须与真实有效记录一致。"""
    room = LiveRoom(
        room_id_str="room-manual-lead-count",
        account_name="人工客资计数账号",
        anchor_name="主播甲",
        platform="douyin",
        status=True,
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        leads_count=0,
    )
    db.add(session)
    db.commit()

    lead = create_lead(
        LeadCreate(
            session_id=session.id,
            lead_phone="13800138000",
            douyin_id="confirmed-user",
            anchor_name="主播甲",
            create_time=datetime(2026, 8, 1, 10, 0),
            is_valid=1,
        ),
        db=db,
    )
    db.refresh(session)
    assert session.leads_count == 1

    delete_lead(lead.id, db=db)
    db.refresh(session)
    assert session.leads_count == 0


def test_match_no_session_today_fallback_to_closest(db):
    """当天没直播但主播有历史场次时，第 4 级按主播就近匹配。"""
    room = LiveRoom(
        room_id_str="room-no-session-today",
        account_name="换号播测试账号",
        anchor_name="主播甲",
        platform="douyin",
        status=True,
    )
    db.add(room)
    db.flush()

    # 主播甲只有 7/26 和 7/28 的直播，7/27 没播
    day_before = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 26, 10, 0),
        live_end_time=datetime(2026, 7, 26, 11, 0),
    )
    day_after = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_status="ended",
        live_start_time=datetime(2026, 7, 28, 10, 0),
        live_end_time=datetime(2026, 7, 28, 11, 0),
    )
    db.add_all([day_before, day_after])
    db.commit()

    # 客资时间在 7/27（主播当天没播）
    item = KeziLeadItem(
        sourceId=301,
        phone="13800138001",
        douyinId="douyin-no-session",
        anchor="主播甲",
        createdAt=datetime(2026, 7, 27, 10, 30),
    )

    session, reason = match_live_session(db, item)
    assert session is not None
    # 应该匹配到 7/26 的场次（时间更近：距 7/26 下播 ~23.5h，距 7/28 开播 ~23.5h，
    # 但 _pick_closest_session 优先找 lead_time 之前结束的）
    assert session.id == day_before.id
    assert reason == "no_session_today"
