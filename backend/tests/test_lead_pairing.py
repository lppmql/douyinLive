"""同主播一分钟客资配对规则测试。"""

from datetime import datetime, timedelta

from app.models.lead_conversion_pairs import LeadConversionPair
from app.models.leads import Lead
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.services.leads.lead_pairing import contact_type, rebuild_lead_conversion_pairs


def _session(db):
    room = LiveRoom(account_name="配对账号", anchor_name="主播甲", room_id_str="lead-pairing-room")
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播甲",
        live_start_time=datetime(2026, 8, 2, 10, 0),
        live_end_time=datetime(2026, 8, 2, 11, 0),
        live_status="ended",
    )
    db.add(session)
    db.flush()
    return session


def test_same_anchor_uses_global_nearest_one_to_one_pairing(db):
    session = _session(db)
    start = session.live_start_time + timedelta(minutes=10)
    db.add_all([
        Lead(session_id=session.id, anchor_name="主播甲", douyin_id="user-a", create_time=start),
        Lead(session_id=session.id, anchor_name="主播甲", lead_phone="13800138000", create_time=start + timedelta(seconds=10)),
        Lead(session_id=session.id, anchor_name="主播甲", lead_phone="13900139000", create_time=start + timedelta(seconds=50)),
        Lead(session_id=session.id, anchor_name="主播甲", douyin_id="user-b", create_time=start + timedelta(seconds=70)),
    ])
    db.flush()

    result = rebuild_lead_conversion_pairs(db)
    db.commit()
    pairs = db.query(LeadConversionPair).order_by(LeadConversionPair.douyin_id).all()

    assert result["pair_count"] == 2
    assert [(item.douyin_id, item.gap_seconds) for item in pairs] == [("user-a", 10), ("user-b", 20)]
    assert session.leads_count == 2


def test_pairing_maximizes_count_before_minimizing_gap(db):
    session = _session(db)
    start = session.live_start_time + timedelta(minutes=10)
    db.add_all([
        Lead(session_id=session.id, anchor_name="主播甲", douyin_id="user-a", create_time=start),
        Lead(session_id=session.id, anchor_name="主播甲", douyin_id="user-b", create_time=start + timedelta(seconds=59)),
        Lead(session_id=session.id, anchor_name="主播甲", lead_phone="13800138000", create_time=start + timedelta(seconds=58)),
        Lead(session_id=session.id, anchor_name="主播甲", lead_phone="13900139000", create_time=start + timedelta(seconds=118)),
    ])
    db.flush()

    result = rebuild_lead_conversion_pairs(db)
    pairs = db.query(LeadConversionPair).order_by(LeadConversionPair.douyin_id).all()

    assert result["pair_count"] == 2
    assert [(item.douyin_id, item.gap_seconds) for item in pairs] == [("user-a", 58), ("user-b", 59)]


def test_rebuild_keeps_existing_pair_identity(db):
    session = _session(db)
    start = session.live_start_time + timedelta(minutes=10)
    db.add_all([
        Lead(session_id=session.id, anchor_name="主播甲", douyin_id="user-a", create_time=start),
        Lead(session_id=session.id, anchor_name="主播甲", lead_phone="13800138000", create_time=start + timedelta(seconds=10)),
    ])
    db.flush()

    rebuild_lead_conversion_pairs(db)
    db.commit()
    first = db.query(LeadConversionPair).one()
    first_identity = (first.id, first.created_at)

    rebuild_lead_conversion_pairs(db)
    db.commit()
    second = db.query(LeadConversionPair).one()

    assert (second.id, second.created_at) == first_identity


def test_different_anchor_or_more_than_60_seconds_never_pairs(db):
    session = _session(db)
    start = session.live_start_time + timedelta(minutes=10)
    db.add_all([
        Lead(session_id=session.id, anchor_name="主播甲", douyin_id="user-a", create_time=start),
        Lead(session_id=session.id, anchor_name="主播乙", lead_phone="13800138000", create_time=start + timedelta(seconds=5)),
        Lead(session_id=session.id, anchor_name="主播甲", lead_phone="13900139000", create_time=start + timedelta(seconds=61)),
    ])
    db.flush()

    result = rebuild_lead_conversion_pairs(db)

    assert result["pair_count"] == 0
    assert db.query(LeadConversionPair).count() == 0


def test_contact_type_distinguishes_phone_and_wechat():
    assert contact_type("+86 13800138000") == "phone"
    assert contact_type("snack_store_2026") == "wechat"
    assert contact_type("微信：snack2026") == "wechat"
    assert contact_type("138****8000") is None
    assert contact_type("not available") is None
    assert contact_type("") is None
