"""同主播一分钟客资配对规则测试。"""

from datetime import datetime, timedelta

from app.models.comments import Comment
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


def test_rebuild_preserves_manual_session_attribution(db):
    first_session = _session(db)
    second_session = LiveSession(
        room_id=first_session.room_id,
        anchor_name="主播甲",
        live_start_time=datetime(2026, 8, 3, 10, 0),
        live_end_time=datetime(2026, 8, 3, 11, 0),
        live_status="ended",
    )
    db.add(second_session)
    start = first_session.live_start_time + timedelta(minutes=10)
    db.add_all([
        Lead(anchor_name="主播甲", douyin_id="user-a", create_time=start),
        Lead(anchor_name="主播甲", lead_phone="13800138000", create_time=start + timedelta(seconds=10)),
    ])
    db.flush()
    rebuild_lead_conversion_pairs(db)
    pair = db.query(LeadConversionPair).one()
    pair.session_id = second_session.id
    pair.attribution_status = "attributed"
    pair.attribution_method = "manual"
    db.commit()
    # 新增更近的联系方式会改变自动最优匹配，但不能拆掉人工确认的一对。
    db.add(
        Lead(
            anchor_name="主播甲",
            lead_phone="13900139000",
            create_time=start + timedelta(seconds=1),
        )
    )
    db.flush()

    rebuild_lead_conversion_pairs(db)
    db.commit()
    db.refresh(pair)

    assert pair.session_id == second_session.id
    assert pair.attribution_method == "manual"


def test_pending_pair_api_only_accepts_strict_candidate(client, db, auth_headers):
    session = _session(db)
    converted_at = session.live_start_time + timedelta(minutes=10)
    db.add_all([
        Lead(anchor_name="主播甲", douyin_id="user-api", create_time=converted_at),
        Lead(
            anchor_name="主播甲",
            lead_phone="13800138000",
            create_time=converted_at + timedelta(seconds=10),
        ),
    ])
    db.flush()
    rebuild_lead_conversion_pairs(db)
    pair = db.query(LeadConversionPair).one()
    assert pair.session_id is None
    # 评论资料可能在配对之后补齐；人工队列此时必须用真实评论抖音号收窄候选场次。
    db.add(
        Comment(
            session_id=session.id,
            user_nickname="测试用户",
            user_douyin_id="user-api",
            comment_content="想了解开店",
            comment_time=converted_at - timedelta(seconds=20),
        )
    )
    db.commit()

    response = client.get(
        "/api/v1/leads/conversion-pairs/pending", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["id"] == pair.id
    assert payload["candidate_sessions"][0]["session_id"] == session.id

    response = client.patch(
        f"/api/v1/leads/conversion-pairs/{pair.id}/attribution",
        headers=auth_headers,
        json={"session_id": session.id},
    )
    assert response.status_code == 200
    db.expire_all()
    assert db.get(LeadConversionPair, pair.id).attribution_method == "manual"


def test_pending_pair_rejects_session_without_matching_comment(client, db, auth_headers):
    session = _session(db)
    converted_at = session.live_start_time + timedelta(minutes=10)
    db.add_all([
        Lead(anchor_name="主播甲", douyin_id="not-in-comments", create_time=converted_at),
        Lead(
            anchor_name="主播甲",
            lead_phone="13800138000",
            create_time=converted_at + timedelta(seconds=10),
        ),
        Comment(
            session_id=session.id,
            user_douyin_id="another-user",
            comment_content="路过",
            comment_time=converted_at,
        ),
    ])
    db.flush()
    rebuild_lead_conversion_pairs(db)
    db.commit()
    pair = db.query(LeadConversionPair).one()

    pending = client.get("/api/v1/leads/conversion-pairs/pending", headers=auth_headers)
    assert pending.status_code == 200
    assert pending.json()[0]["candidate_sessions"] == []
    response = client.patch(
        f"/api/v1/leads/conversion-pairs/{pair.id}/attribution",
        headers=auth_headers,
        json={"session_id": session.id},
    )
    assert response.status_code == 409


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
