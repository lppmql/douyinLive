"""知识库完整正文与场次明细入库测试。"""

from datetime import datetime

from app.models.knowledge_base import KnowledgeBase
from app.models.live_metrics import LiveMetric
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.services.ai.kb_service import _upsert_kb_item, save_session_data_to_kb


def test_kb_longtext_is_not_silently_truncated(db):
    content = "真实直播话术" * 12000
    room = LiveRoom(account_name="长文本测试账号", anchor_name="长文本主播", room_id_str="kb-longtext-room")
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, anchor_name="长文本主播")
    db.add(session)
    db.flush()

    inserted = _upsert_kb_item(db, session.id, "transcript", "优质话术", "完整话术", content)

    row = db.query(KnowledgeBase).filter(KnowledgeBase.session_id == session.id).one()
    assert inserted == 1
    assert row.content == content
    assert len(row.content) > 60000


def test_session_knowledge_contains_complete_fields_and_raw_minute_metrics(db):
    room = LiveRoom(account_name="知识测试账号", anchor_name="知识测试主播", room_id_str="kb-complete-room")
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="知识测试主播",
        douyin_id="real_anchor_id",
        live_start_time=datetime(2026, 7, 23, 9, 0, 0),
        live_duration_seconds=4800,
        gift_count=7,
        marketing_traffic_ratio=0.25,
    )
    db.add(session)
    db.flush()
    db.add(
        LiveMetric(
            id=1,
            session_id=session.id,
            metric_time=datetime(2026, 7, 23, 9, 1, 0),
            online_count=18,
            natural_traffic_count=11,
            marketing_traffic_count=7,
        )
    )
    db.commit()

    save_session_data_to_kb(db, session.id)

    row = db.query(KnowledgeBase).filter(
        KnowledgeBase.session_id == session.id,
        KnowledgeBase.source_type == "live_data",
    ).one()
    assert '"gift_count": 7' in row.content
    assert '"marketing_traffic_ratio": "0.2500"' in row.content
    assert '"natural_traffic_count": 11' in row.content
    assert "逐分钟指标" in row.content
    assert "m3u8" not in row.content
